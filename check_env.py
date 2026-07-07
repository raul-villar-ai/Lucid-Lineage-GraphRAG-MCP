import os
import sys
from neo4j import GraphDatabase
from dotenv import load_dotenv, find_dotenv

# Windows consoles default to cp1252 and cannot encode the ✅/❌ status glyphs,
# which raises UnicodeEncodeError. Force UTF-8 on the output streams first.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Explicitly find and load the .env file
dotenv_path = find_dotenv()
print(f"DEBUG: Found and loading .env at: {dotenv_path}")
load_dotenv(dotenv_path=dotenv_path, override=True)

uri = os.getenv("NEO4J_URI")
user = os.getenv("NEO4J_USER")
password = os.getenv("NEO4J_PASSWORD")

print(f"DEBUG: Attempting connection to: {uri} with user: {user}")

try:
    # Use simple timeout to catch connection issues early
    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    print("\n✅ SUCCESS: Authentication and Connectivity confirmed!")
    driver.close()
except Exception as e:
    print(f"\n❌ FAILED: Connection error: {e}")