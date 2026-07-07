// ============================================================================
// LUCID LINEAGE: ENTERPRISE GRAPH SEED SCRIPT (RESTORED ORIGINAL)
// ============================================================================

// 0. WIPE OLD SCHEMA AND DATA (To ensure a clean 117-record slate)
DROP CONSTRAINT session_id_unique IF EXISTS;
DROP INDEX message_timestamp_idx IF EXISTS;
DROP INDEX finding_timestamp_idx IF EXISTS;
MATCH (n) DETACH DELETE n;

// 1. Create Compliance Boundaries
CREATE (gdpr_zone:Compliance_Boundary {name: 'GDPR_EU_Privacy', policy: 'No_Unencrypted_Offshore_Transfer', tier: 'Strict'})
CREATE (sox_financial:Compliance_Boundary {name: 'SOX_Financial_Regs', policy: 'Immutable_Audit_Trail_Required', tier: 'Critical'})
CREATE (ccpa_zone:Compliance_Boundary {name: 'CCPA_US_Privacy', policy: 'Standard_Privacy_Controls', tier: 'Elevated'})
CREATE (internal_ip:Compliance_Boundary {name: 'Corporate_IP_Vault', policy: 'Zero_External_Network_Access', tier: 'Critical'})

// 2. Create Enterprise Compute Nodes (Cloud & On-Prem)
CREATE (eu_cloud_primary:Compute_Node {name: 'EU_Frankfurt_Cloud_01', type: 'Public_Cloud', encryption: 'AES-256'})
CREATE (eu_cloud_dr:Compute_Node {name: 'EU_Paris_DR_Cluster', type: 'Public_Cloud', encryption: 'AES-256'})
CREATE (us_cloud_east:Compute_Node {name: 'US_East_Analytics_Pool', type: 'Public_Cloud', encryption: 'Standard'})
CREATE (us_onprem_vault:Compute_Node {name: 'US_HQ_Mainframe_Vault', type: 'Air_Gapped_OnPrem', encryption: 'Hardware_Level'})
CREATE (apac_edge:Compute_Node {name: 'APAC_Edge_Gateway', type: 'Edge_Node', encryption: 'Transit_Only'})

// 3. Create Data Assets
CREATE (eu_customer_db:Data_Asset {name: 'EU_Customer_PII_Master', classification: 'Highly_Restricted'})
CREATE (global_ledger:Data_Asset {name: 'Q3_Global_Financial_Ledger', classification: 'Restricted'})
CREATE (trade_secrets:Data_Asset {name: 'NextGen_Algorithm_SourceCode', classification: 'Highly_Restricted'})
CREATE (marketing_metrics:Data_Asset {name: 'Global_Ad_Engagement_Metrics', classification: 'Public'})
CREATE (us_payroll:Data_Asset {name: 'North_America_Payroll_DB', classification: 'Restricted'})
CREATE (apac_telemetry:Data_Asset {name: 'APAC_IoT_Telemetry_Logs', classification: 'Internal_Only'})

// 4. Create Service Accounts & Identities
CREATE (etl_bot_eu:Service_Account {name: 'SVC_ETL_EU_Sync', role: 'Automated_Pipeline', privilege: 'Read_Write'})
CREATE (global_admin:Service_Account {name: 'GRP_Global_SysAdmins', role: 'Human_Admin', privilege: 'SuperUser'})
CREATE (auditor_readonly:Service_Account {name: 'SVC_Compliance_Auditor', role: 'Automated_Monitor', privilege: 'Read_Only'})
CREATE (marketing_api:Service_Account {name: 'SVC_Marketing_Dashboard', role: 'API_Gateway', privilege: 'Read_Only'})

// ============================================================================
// 5. MAP THE ARCHITECTURE (The Lineage Relationships)
// ============================================================================

// Apply Compliance Governance to Compute Nodes
MERGE (eu_cloud_primary)-[:GOVERNED_BY]->(gdpr_zone)
MERGE (eu_cloud_dr)-[:GOVERNED_BY]->(gdpr_zone)
MERGE (us_cloud_east)-[:GOVERNED_BY]->(ccpa_zone)
MERGE (us_onprem_vault)-[:GOVERNED_BY]->(internal_ip)
MERGE (us_onprem_vault)-[:GOVERNED_BY]->(sox_financial)

// Map Primary Storage Locations
MERGE (eu_customer_db)-[:STORED_ON]->(eu_cloud_primary)
MERGE (global_ledger)-[:STORED_ON]->(us_onprem_vault)
MERGE (trade_secrets)-[:STORED_ON]->(us_onprem_vault)
MERGE (marketing_metrics)-[:STORED_ON]->(us_cloud_east)
MERGE (us_payroll)-[:STORED_ON]->(us_onprem_vault)
MERGE (apac_telemetry)-[:STORED_ON]->(apac_edge)

// Map Legitimate Data Replications & Backups
MERGE (eu_customer_db)-[:REPLICATED_TO {method: 'Encrypted_Sync'}]->(eu_cloud_dr)
MERGE (global_ledger)-[:REPLICATED_TO {method: 'Daily_Batch'}]->(eu_cloud_primary)

// Map Service Account Access
MERGE (global_admin)-[:HAS_ACCESS]->(eu_customer_db)
MERGE (global_admin)-[:HAS_ACCESS]->(global_ledger)
MERGE (global_admin)-[:HAS_ACCESS]->(trade_secrets)
MERGE (auditor_readonly)-[:HAS_ACCESS]->(global_ledger)
MERGE (marketing_api)-[:HAS_ACCESS]->(marketing_metrics)
MERGE (etl_bot_eu)-[:HAS_ACCESS]->(eu_customer_db)

// ============================================================================
// 6. INJECT INTENTIONAL COMPLIANCE VIOLATIONS
// ============================================================================
MERGE (eu_customer_db)-[:REPLICATED_TO {method: 'Shadow_IT_Pipeline'}]->(us_cloud_east)
MERGE (marketing_api)-[:HAS_ACCESS]->(us_payroll)
MERGE (trade_secrets)-[:STORED_ON]->(apac_edge);

// ============================================================================
// 7. CONTEXT GRAPH & AUDIT MEMORY PREPARATION
// ============================================================================
CREATE CONSTRAINT session_id_unique IF NOT EXISTS FOR (s:Session) REQUIRE s.id IS UNIQUE;
CREATE INDEX message_timestamp_idx IF NOT EXISTS FOR (m:Message) ON (m.timestamp);
CREATE INDEX finding_timestamp_idx IF NOT EXISTS FOR (f:Audit_Finding) ON (f.timestamp);

// ============================================================================
// 8. SOVEREIGN BOUNDARY TRACE SCENARIO
// ============================================================================
// Updated to use the canonical schema (Data_Asset, Compute_Node, REPLICATED_TO, Compliance_Boundary)

// Match the existing CCPA boundary from earlier in the script
MATCH (ccpa_zone:Compliance_Boundary {name: 'CCPA_US_Privacy'})

// In a real scenario, we might have a specific UK boundary
MERGE (uk_sovereign:Compliance_Boundary {name: 'UK_Sovereign_Boundary', policy: 'No_Offshore_Without_Consent', tier: 'Strict'})

MERGE (prod_node:Compute_Node {name: 'uk-prod-worker-01', type: 'Public_Cloud', encryption: 'AES-256'})
MERGE (backup_node:Compute_Node {name: 'us-cold-storage-99', type: 'Public_Cloud', encryption: 'AES-256'})

MERGE (manifest:Data_Asset {name: 'Supply_Chain_Manifest', classification: 'Restricted'})
MERGE (manifest)-[:STORED_ON]->(prod_node)
MERGE (manifest)-[:REPLICATED_TO]->(backup_node)

MERGE (dummy_asset:Data_Asset {name: 'Legacy_Customer_Archive', classification: 'Public'})
MERGE (dummy_asset)-[:REPLICATED_TO]->(backup_node)

MERGE (prod_node)-[:GOVERNED_BY]->(uk_sovereign)
MERGE (backup_node)-[:GOVERNED_BY]->(ccpa_zone);

// ============================================================================
// 9. EXTENDED ENTERPRISE TOPOLOGY (enrichment for robust test coverage)
// ============================================================================
// Additive only: this section does NOT remove any Section 1-8 nodes or edges, so
// the existing test scenarios (TC1-TC3) remain intact. It is written entirely
// with MERGE (matching the Section 1-8 nodes it links to by name) so it is
// idempotent and safe to re-run. Goals:
//   * Give APAC_Edge_Gateway explicit UPSTREAM data pipelines so "upstream
//     dependencies feeding into the APAC gateway" (TC3) is unambiguous.
//   * Add a second, clean cross-boundary leak (PCI -> APAC) for TC2-style audits.
//   * Broaden boundaries / nodes / assets / classifications for future tests.

// --- New compliance boundaries -------------------------------------------
MERGE (apac_sov:Compliance_Boundary {name: 'APAC_Data_Sovereignty'})
  ON CREATE SET apac_sov.policy = 'Regional_Data_Residency_Required', apac_sov.tier = 'Strict'
MERGE (pci:Compliance_Boundary {name: 'PCI_DSS_Payments'})
  ON CREATE SET pci.policy = 'Cardholder_Data_Isolation', pci.tier = 'Critical'
MERGE (hipaa:Compliance_Boundary {name: 'HIPAA_Health_Data'})
  ON CREATE SET hipaa.policy = 'PHI_Encryption_And_Access_Control', hipaa.tier = 'Strict'

// --- New compute nodes ----------------------------------------------------
MERGE (tokyo:Compute_Node {name: 'APAC_Tokyo_Cloud_01'})
  ON CREATE SET tokyo.type = 'Public_Cloud', tokyo.encryption = 'AES-256'
MERGE (sg_analytics:Compute_Node {name: 'APAC_Singapore_Analytics'})
  ON CREATE SET sg_analytics.type = 'Public_Cloud', sg_analytics.encryption = 'Standard'
MERGE (pay_proc:Compute_Node {name: 'US_Payments_Processor'})
  ON CREATE SET pay_proc.type = 'Private_Cloud', pay_proc.encryption = 'AES-256'
MERGE (eu_health:Compute_Node {name: 'EU_Health_Cluster'})
  ON CREATE SET eu_health.type = 'Private_Cloud', eu_health.encryption = 'AES-256'

// --- Governance for the new nodes ----------------------------------------
MERGE (tokyo)-[:GOVERNED_BY]->(apac_sov)
MERGE (sg_analytics)-[:GOVERNED_BY]->(apac_sov)
MERGE (pay_proc)-[:GOVERNED_BY]->(pci)
MERGE (eu_health)-[:GOVERNED_BY]->(hipaa)

// --- New data assets ------------------------------------------------------
MERGE (supply_tel:Data_Asset {name: 'Global_Supply_Telemetry'})
  ON CREATE SET supply_tel.classification = 'Internal_Only'
MERGE (card_vault:Data_Asset {name: 'Cardholder_Transaction_Vault'})
  ON CREATE SET card_vault.classification = 'Highly_Restricted'
MERGE (phr:Data_Asset {name: 'Patient_Health_Records'})
  ON CREATE SET phr.classification = 'Highly_Restricted'
MERGE (apac_sales:Data_Asset {name: 'APAC_Regional_Sales'})
  ON CREATE SET apac_sales.classification = 'Restricted'
MERGE (vendor_repo:Data_Asset {name: 'Vendor_Contract_Repository'})
  ON CREATE SET vendor_repo.classification = 'Restricted'

// --- New service accounts -------------------------------------------------
MERGE (svc_apac:Service_Account {name: 'SVC_APAC_Ingest_Pipeline'})
  ON CREATE SET svc_apac.role = 'Automated_Pipeline', svc_apac.privilege = 'Read_Write'
MERGE (svc_pay:Service_Account {name: 'SVC_Payments_Gateway'})
  ON CREATE SET svc_pay.role = 'API_Gateway', svc_pay.privilege = 'Read_Write'

// --- Anchor existing Section 1-2 nodes we link to (matched by name) --------
MERGE (apac_edge:Compute_Node {name: 'APAC_Edge_Gateway'})
MERGE (us_vault:Compute_Node {name: 'US_HQ_Mainframe_Vault'})

// --- Well-governed placements (compliant; no cross-boundary) --------------
MERGE (phr)-[:STORED_ON]->(eu_health)
MERGE (vendor_repo)-[:STORED_ON]->(tokyo)
MERGE (apac_sales)-[:STORED_ON]->(tokyo)

// --- Explicit UPSTREAM pipelines feeding INTO APAC_Edge_Gateway (TC3) ------
MERGE (supply_tel)-[:STORED_ON]->(us_vault)
MERGE (supply_tel)-[:REPLICATED_TO {method: 'Edge_Sync'}]->(apac_edge)
MERGE (apac_sales)-[:REPLICATED_TO {method: 'Regional_Aggregation'}]->(apac_edge)

// --- New INTENTIONAL cross-boundary violation (PCI -> APAC) ----------------
MERGE (card_vault)-[:STORED_ON]->(pay_proc)
MERGE (card_vault)-[:REPLICATED_TO {method: 'Shadow_Analytics_Pipeline'}]->(sg_analytics)

// --- New service-account access edges --------------------------------------
MERGE (svc_apac)-[:HAS_ACCESS]->(supply_tel)
MERGE (svc_apac)-[:HAS_ACCESS]->(apac_sales)
MERGE (svc_pay)-[:HAS_ACCESS]->(card_vault);