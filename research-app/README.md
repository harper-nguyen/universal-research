# Universal Research App

A minimal, evidence-based research tool powered by the `universal-research` skill and Google Gemini.

## Prerequisites
- Python 3.10+
- A Gemini API Key (free at [aistudio.google.com](https://aistudio.google.com))

---

## Run Locally

```bash
# 1. Navigate to the project
cd ~/AI/universal-skills/research/research-app

# 2. Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Add your API key
cp .env.example .env
# Edit .env → set GEMINI_API_KEY=your_actual_key

# 5. Run
streamlit run app.py
# Open http://localhost:8501
```

---

## Deploy to Streamlit Community Cloud (Free)

This is the recommended way to use the app from any device without running it locally.

### Step 1 — Push to GitHub
Create a **private** GitHub repository and push the contents of this `research-app/` folder to the **root** of that repo.

```bash
cd ~/AI/universal-skills/research/research-app
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

### Step 2 — Connect to Streamlit Cloud
1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
2. Click **New app**.
3. Select your repository, branch (`main`), and set the Main file path to `app.py`.
4. Click **Advanced settings**.

### Step 3 — Add your API Key (Secrets)
In the **Secrets** field, paste:
```toml
GEMINI_API_KEY = "your_actual_gemini_api_key"
```
This keeps your key private and out of the source code.

### Step 4 — Deploy
Click **Deploy**. Streamlit will build and launch your app at a public URL like:
`https://your-app-name.streamlit.app`

---

## How it works
- **Skill Loading**: `app.py` reads `SKILL.md` from the same directory and injects it as the system instruction to the AI model.
- **Web Search**: The app uses Gemini's built-in Google Search tool to gather real evidence for every query.
- **No fabrication**: The AI is constrained by the `universal-research` skill to only cite verified sources.
