-- Run in the Fabric Warehouse SQL editor after the Warehouse item is created.
-- The source Lakehouse SQL endpoint must expose dbo.dim_property, dbo.dim_date,
-- dbo.fact_assessment, dbo.fact_sale, and dbo.fact_appeal.

CREATE SCHEMA assessment;
GO

CREATE TABLE assessment.DimProperty
(
    PropertyKey bigint NOT NULL,
    ParcelId varchar(20) NOT NULL,
    NeighborhoodId varchar(10) NOT NULL,
    NeighborhoodName varchar(100) NOT NULL,
    MarketArea varchar(30) NOT NULL,
    PropertyClassCode varchar(10) NOT NULL,
    SyntheticAddress varchar(150) NOT NULL,
    Latitude float NOT NULL,
    Longitude float NOT NULL,
    LotAreaSquareMetres float NOT NULL,
    ZoningCode varchar(12) NOT NULL,
    IsSynthetic bit NOT NULL
);
GO

CREATE TABLE assessment.DimDate
(
    DateKey int NOT NULL,
    [Date] date NOT NULL,
    [Year] int NOT NULL,
    [Quarter] int NOT NULL,
    [Month] int NOT NULL,
    MonthName varchar(20) NOT NULL
);
GO

CREATE TABLE assessment.FactAssessment
(
    AssessmentId varchar(30) NOT NULL,
    PropertyKey bigint NOT NULL,
    ValuationDateKey int NOT NULL,
    TaxYear int NOT NULL,
    LandValue decimal(18,2) NOT NULL,
    ImprovementValue decimal(18,2) NOT NULL,
    AssessedValue decimal(18,2) NOT NULL,
    EstimatedTax decimal(18,2) NOT NULL,
    ConfidenceScore decimal(9,4) NOT NULL
);
GO

CREATE TABLE assessment.FactSale
(
    SaleId varchar(30) NOT NULL,
    PropertyKey bigint NOT NULL,
    SaleDateKey int NOT NULL,
    SalePrice decimal(18,2) NOT NULL,
    IsArmsLength bit NOT NULL
);
GO

CREATE TABLE assessment.FactAppeal
(
    AppealId varchar(30) NOT NULL,
    PropertyKey bigint NOT NULL,
    SubmittedDateKey int NOT NULL,
    TaxYear int NOT NULL,
    ReasonCode varchar(40) NOT NULL,
    Status varchar(20) NOT NULL,
    Outcome varchar(30) NULL,
    RequestedAdjustmentPct decimal(9,2) NOT NULL,
    GroundTruthSentiment varchar(20) NOT NULL,
    AiSentiment varchar(20) NULL,
    AiTheme varchar(100) NULL,
    AiUrgencyScore decimal(9,4) NULL,
    ResolvedFlag bit NOT NULL
);
GO

CREATE VIEW assessment.vwNeighborhoodEquity AS
SELECT
    p.NeighborhoodName,
    p.PropertyClassCode,
    a.TaxYear,
    COUNT_BIG(*) AS AssessmentCount,
    AVG(a.AssessedValue) AS AverageAssessedValue,
    AVG(CASE WHEN s.SalePrice > 0 THEN a.AssessedValue / s.SalePrice END) AS AverageAssessmentToSaleRatio,
    SUM(CASE WHEN ap.AppealId IS NULL THEN 0 ELSE 1 END) AS AppealCount
FROM assessment.FactAssessment a
JOIN assessment.DimProperty p ON p.PropertyKey = a.PropertyKey
LEFT JOIN assessment.FactSale s ON s.PropertyKey = a.PropertyKey
LEFT JOIN assessment.FactAppeal ap ON ap.PropertyKey = a.PropertyKey AND ap.TaxYear = a.TaxYear
GROUP BY p.NeighborhoodName, p.PropertyClassCode, a.TaxYear;
GO

-- Load pattern: use COPY INTO from Lakehouse-exported Parquet or a Fabric pipeline.
-- Do not use INSERT...SELECT across endpoints unless your tenant explicitly supports it.

