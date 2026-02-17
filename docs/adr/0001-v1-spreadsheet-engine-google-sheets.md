# ADR 0001: Use Google Sheets API as V1 spreadsheet engine

## Status
Accepted

## Context
The PRD requires deterministic spreadsheet-native valuation logic with auditable formulas and outputs.

## Decision
Use Google Sheets API as the V1 compute layer for workbook creation/copy, range writes, formula evaluation, output reads, and logbook appends.

## Consequences
- Pros: lower setup burden, inspectable model, strong auditability, cloud-native sharing.
- Tradeoffs: API quotas, spreadsheet formula portability constraints, and Drive permission management.
