# Fabric notebook source. Attach the "PropertyAssessmentLakehouse" Lakehouse before running.
# PARAMETERS
source_root = "Files/landing/property-assessment"
appeals_path = f"{source_root}/adls/assessment_appeals.parquet"
profiles_path = f"{source_root}/cosmos/property_profiles.json"
sql_root = f"{source_root}/sql"

# CELL ------------------------------------------------------------------------
from pyspark.sql import functions as F
from pyspark.sql.types import BooleanType, DoubleType, IntegerType, StringType, StructField, StructType

spark.conf.set("spark.databricks.delta.schema.autoMerge.enabled", "true")

# CELL ------------------------------------------------------------------------
# Bronze: preserve source shape and add ingestion metadata.
def with_audit(df, source_name):
    return (df.withColumn("_source", F.lit(source_name))
              .withColumn("_ingestedAt", F.current_timestamp())
              .withColumn("_recordHash", F.sha2(F.to_json(F.struct(*df.columns)), 256)))

bronze_parcels = with_audit(spark.read.option("header", True).option("inferSchema", True).csv(f"{sql_root}/parcels.csv"), "azure-sql-parcel")
bronze_assessments = with_audit(spark.read.option("header", True).option("inferSchema", True).csv(f"{sql_root}/assessments.csv"), "azure-sql-assessment")
bronze_sales = with_audit(spark.read.option("header", True).option("inferSchema", True).csv(f"{sql_root}/sales.csv"), "azure-sql-sale")
bronze_profiles = with_audit(spark.read.option("multiLine", True).json(profiles_path), "cosmos-property-profile")
bronze_appeals = with_audit(spark.read.parquet(appeals_path), "adls-appeal")

for name, frame in {
    "bronze_parcel": bronze_parcels,
    "bronze_assessment": bronze_assessments,
    "bronze_sale": bronze_sales,
    "bronze_property_profile": bronze_profiles,
    "bronze_appeal": bronze_appeals
}.items():
    frame.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(name)

# CELL ------------------------------------------------------------------------
# Silver: typed, de-duplicated, quality-checked records.
def assert_no_nulls(df, column, label):
    failures = df.filter(F.col(column).isNull()).count()
    assert failures == 0, f"{label}: {failures} null {column} values"

silver_parcel = (bronze_parcels
    .select("parcelId", "parcelNumber", "neighborhoodId", "neighborhoodName", "marketArea",
            "propertyClassCode", "syntheticAddress", F.col("latitude").cast("double"),
            F.col("longitude").cast("double"), F.col("lotAreaSquareMetres").cast("double"),
            "zoningCode", F.col("isSynthetic").cast("boolean"))
    .dropDuplicates(["parcelId"]))

silver_assessment = (bronze_assessments
    .select("assessmentId", "parcelId", F.col("taxYear").cast("int"), F.to_date("valuationDate").alias("valuationDate"),
            F.col("landValue").cast("double"), F.col("improvementValue").cast("double"),
            F.col("assessedValue").cast("double"), F.col("confidenceScore").cast("double"),
            "assessmentStatus", "currencyCode", F.col("isSynthetic").cast("boolean"))
    .dropDuplicates(["assessmentId"]))

silver_sale = (bronze_sales
    .select("saleId", "parcelId", F.to_date("saleDate").alias("saleDate"), F.col("salePrice").cast("double"),
            "saleType", F.col("isArmsLength").cast("boolean"), "currencyCode", F.col("isSynthetic").cast("boolean"))
    .dropDuplicates(["saleId"]))

silver_appeal = (bronze_appeals
    .select("appealId", "parcelId", F.col("taxYear").cast("int"), F.to_date("submittedDate").alias("submittedDate"),
            "reasonCode", "narrative", F.col("requestedAdjustmentPct").cast("double"), "status", "outcome",
            F.to_date("resolvedDate").alias("resolvedDate"), "groundTruthSentiment",
            F.lit(None).cast("string").alias("aiSentiment"),
            F.lit(None).cast("string").alias("aiSummary"),
            F.lit(None).cast("string").alias("aiTheme"),
            F.lit(None).cast("double").alias("aiUrgencyScore"),
            F.col("synthetic").cast("boolean"))
    .dropDuplicates(["appealId"]))

for label, frame in {"parcel": silver_parcel, "assessment": silver_assessment, "sale": silver_sale, "appeal": silver_appeal}.items():
    assert_no_nulls(frame, "parcelId", label)
    unknown = frame.select("parcelId").distinct().join(silver_parcel.select("parcelId"), "parcelId", "left_anti").count()
    assert unknown == 0, f"{label}: {unknown} unknown parcelId values"

arithmetic_failures = silver_assessment.filter(F.abs(F.col("assessedValue") - F.col("landValue") - F.col("improvementValue")) > .01).count()
assert arithmetic_failures == 0, f"assessment arithmetic failures: {arithmetic_failures}"

for name, frame in {"silver_parcel": silver_parcel, "silver_assessment": silver_assessment, "silver_sale": silver_sale, "silver_appeal": silver_appeal}.items():
    frame.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(name)

# CELL ------------------------------------------------------------------------
# Gold: dimensional outputs. AI columns are intentionally nullable and enrichment-ready.
dim_property = silver_parcel.withColumn("propertyKey", F.xxhash64("parcelId"))
dim_date = (spark.range(0, 1096)
    .select(F.date_add(F.lit("2024-01-01"), F.col("id").cast("int")).alias("date"))
    .select(F.date_format("date", "yyyyMMdd").cast("int").alias("dateKey"), "date",
            F.year("date").alias("year"), F.quarter("date").alias("quarter"),
            F.month("date").alias("month"), F.date_format("date", "MMMM").alias("monthName")))

fact_assessment = (silver_assessment.join(dim_property.select("parcelId", "propertyKey"), "parcelId")
    .withColumn("valuationDateKey", F.date_format("valuationDate", "yyyyMMdd").cast("int"))
    .withColumn("estimatedTax", F.round(F.col("assessedValue") * F.lit(.0128), 2)))

fact_sale = (silver_sale.join(dim_property.select("parcelId", "propertyKey"), "parcelId")
    .withColumn("saleDateKey", F.date_format("saleDate", "yyyyMMdd").cast("int")))

fact_appeal = (silver_appeal.join(dim_property.select("parcelId", "propertyKey"), "parcelId")
    .withColumn("submittedDateKey", F.date_format("submittedDate", "yyyyMMdd").cast("int"))
    .withColumn("resolvedFlag", F.col("status") == "resolved"))

for name, frame in {"dim_property": dim_property, "dim_date": dim_date, "fact_assessment": fact_assessment, "fact_sale": fact_sale, "fact_appeal": fact_appeal}.items():
    frame.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(name)

# CELL ------------------------------------------------------------------------
# Explore:
# 1. Which neighborhoods have the widest assessment-to-sale ratio spread?
# 2. Do appeal reasons correlate with condition, class, or confidence score?
# 3. Which nullable AI enrichment columns would most improve triage?
display(fact_assessment.groupBy("taxYear").agg(F.count("*").alias("assessments"), F.round(F.avg("assessedValue"), 2).alias("avgAssessedValue")))
