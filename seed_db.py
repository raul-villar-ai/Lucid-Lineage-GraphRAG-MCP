import os
import re
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

def run_seed():
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD")
    
    with open('data/init_graph.cypher', 'r') as f:
        content = f.read()

    # Remove comments
    content = re.sub(r'//.*', '', content)
    
    # Split by semicolon
    queries = [q.strip() for q in content.split(';') if q.strip()]

    driver = GraphDatabase.driver(uri, auth=(user, password))
    with driver.session() as session:
        for query in queries:
            if query:
                try:
                    session.run(query)
                except Exception as e:
                    print(f"Error executing: {query}\n{e}")
                    
    driver.close()
    print("Database seeded successfully.")

if __name__ == "__main__":
    run_seed()
