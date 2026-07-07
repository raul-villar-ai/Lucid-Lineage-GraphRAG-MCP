import os
import sys
import requests
from dotenv import load_dotenv

# Windows consoles default to cp1252 and cannot encode the ✅/❌ status glyphs,
# which raises UnicodeEncodeError. Force UTF-8 on the output streams first.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")

url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
response = requests.get(url, timeout=15)

if response.status_code == 200:
    print("✅ Your API Key has access to these models:\n")
    models = response.json().get('models', [])
    for m in models:
        # Only print models that support text generation
        if 'generateContent' in m.get('supportedGenerationMethods', []):
            print(f" - {m.get('name').replace('models/', '')}")
else:
    print(f"❌ Error connecting to Google API: {response.status_code}")
    print(response.text)