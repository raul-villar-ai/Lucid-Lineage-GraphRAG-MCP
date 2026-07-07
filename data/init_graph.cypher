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