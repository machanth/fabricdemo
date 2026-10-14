SET XACT_ABORT ON;
BEGIN TRANSACTION;

IF SCHEMA_ID('assessment') IS NULL EXEC('CREATE SCHEMA assessment');

DROP VIEW IF EXISTS assessment.vwPropertyTaxRoll;
DROP TABLE IF EXISTS dbo.Sale;
DROP TABLE IF EXISTS dbo.Assessment;
DROP TABLE IF EXISTS dbo.Building;
DROP TABLE IF EXISTS dbo.Parcel;

CREATE TABLE dbo.Parcel
(
    parcelId varchar(20) NOT NULL PRIMARY KEY,
    parcelNumber varchar(30) NOT NULL UNIQUE,
    neighborhoodId varchar(10) NOT NULL,
    neighborhoodName nvarchar(100) NOT NULL,
    marketArea nvarchar(30) NOT NULL,
    propertyClassCode varchar(10) NOT NULL,
    syntheticAddress nvarchar(150) NOT NULL,
    latitude decimal(9,6) NOT NULL,
    longitude decimal(9,6) NOT NULL,
    lotAreaSquareMetres decimal(14,2) NOT NULL,
    zoningCode varchar(12) NOT NULL,
    isSynthetic bit NOT NULL
);

CREATE TABLE dbo.Building
(
    buildingId int NOT NULL PRIMARY KEY,
    parcelId varchar(20) NOT NULL,
    buildingType nvarchar(50) NOT NULL,
    yearBuilt smallint NOT NULL,
    floorAreaSquareMetres decimal(14,2) NOT NULL,
    storeys smallint NOT NULL,
    conditionCode varchar(12) NOT NULL,
    isSynthetic bit NOT NULL,
    CONSTRAINT FK_Building_Parcel FOREIGN KEY (parcelId) REFERENCES dbo.Parcel(parcelId)
);

CREATE TABLE dbo.Assessment
(
    assessmentId varchar(30) NOT NULL PRIMARY KEY,
    parcelId varchar(20) NOT NULL,
    taxYear smallint NOT NULL,
    valuationDate date NOT NULL,
    landValue decimal(18,2) NOT NULL,
    improvementValue decimal(18,2) NOT NULL,
    assessedValue decimal(18,2) NOT NULL,
    confidenceScore decimal(9,4) NOT NULL,
    assessmentStatus varchar(20) NOT NULL,
    currencyCode char(3) NOT NULL,
    isSynthetic bit NOT NULL,
    CONSTRAINT UQ_Assessment_ParcelYear UNIQUE (parcelId, taxYear),
    CONSTRAINT CK_Assessment_Total CHECK (assessedValue = landValue + improvementValue),
    CONSTRAINT FK_Assessment_Parcel FOREIGN KEY (parcelId) REFERENCES dbo.Parcel(parcelId)
);

CREATE TABLE dbo.Sale
(
    saleId varchar(30) NOT NULL PRIMARY KEY,
    parcelId varchar(20) NOT NULL,
    saleDate date NOT NULL,
    salePrice decimal(18,2) NOT NULL,
    saleType varchar(20) NOT NULL,
    isArmsLength bit NOT NULL,
    currencyCode char(3) NOT NULL,
    isSynthetic bit NOT NULL,
    CONSTRAINT FK_Sale_Parcel FOREIGN KEY (parcelId) REFERENCES dbo.Parcel(parcelId)
);

EXEC('CREATE VIEW assessment.vwPropertyTaxRoll AS
SELECT p.parcelId, p.neighborhoodName, p.propertyClassCode, a.taxYear,
       a.landValue, a.improvementValue, a.assessedValue,
       CAST(a.assessedValue * 0.0128 AS decimal(18,2)) AS illustrativeEstimatedTax,
       a.currencyCode, p.isSynthetic
FROM dbo.Parcel p JOIN dbo.Assessment a ON a.parcelId = p.parcelId');

COMMIT TRANSACTION;

