"""Quick script to list available Gemini models on the configured API key."""
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key or api_key == "mock":
    print("ERROR: Set a real GEMINI_API_KEY in .env first.")
    exit(1)

client = genai.Client(api_key=api_key)

print("Fetching available models...\n")
models = client.models.list()
for m in models:
    methods = getattr(m, 'supported_actions', None) or getattr(m, 'supported_generation_methods', [])
    if 'generateContent' in str(methods):
        print(f"  ✅ {m.name}")
