# Smart Bug Tracking & QA Automation Assistant (MAS)

A locally-hosted Multi-Agent System that automates bug analysis, test case generation, root cause detection, and bug report compilation using LLM-powered agents orchestrated with LangGraph.

## Architecture

```
User submits bug --> Frontend (React + Vite)
                          |
                    Backend (FastAPI)
                          |
                +-----------------------------------+
                |       LangGraph Pipeline          |
                +-----------------------------------+
                | Agent 1: Bug Analyzer             |
                |              |                    |
                | Agent 2: Test Case Generator      |
                |              |                    |
                | Agent 3: Root Cause Analyzer      |
                |              |                    |
                | Agent 4: Bug Report Generator     |
                +-----------------------------------+
                          |
                    Ollama (Local LLM)
```

## Tech Stack

| Component     | Technology                         |
|---------------|------------------------------------|
| LLM Engine    | Ollama (phi3:mini / llama3:8b)     |
| Orchestration | LangGraph                          |
| Backend       | FastAPI + Python                   |
| Frontend      | React + Vite                       |
| State Mgmt    | TypedDict shared across all agents |
| Logging       | Structured JSON logs per run       |

---

## Prerequisites

Install the following before running the project.

### 1. Python 3.10 or higher

- **macOS:**
  ```bash
  brew install python
  ```
- **Windows:**
  Download from [python.org](https://www.python.org/downloads/) and install. **Make sure to tick "Add Python to PATH"** during installation.

### 2. Node.js 18 or higher

- **macOS:**
  ```bash
  brew install node
  ```
- **Windows:**
  Download the LTS version from [nodejs.org](https://nodejs.org/) and install.

### 3. Ollama

- **macOS:**
  ```bash
  brew install ollama
  ```
- **Windows:**
  Download the installer from [ollama.com](https://ollama.com/) and install.

### 4. Pull the LLM Model

After installing Ollama, pull the default model:

```bash
ollama pull phi3:mini
```

> **Note:** You can also use other models like `llama3:8b` or `qwen`. The app has a model dropdown to switch models at runtime. Use `phi3:mini` if your device has limited resources.

---

## Getting Started

### Clone the Repository

```bash
git clone https://github.com/<your-username>/Smart-Bug-Tracking-and-QA-Automation-Assistant-MAS-.git
cd Smart-Bug-Tracking-and-QA-Automation-Assistant-MAS-
```

---

## Backend Setup

Open a terminal and navigate to the backend folder:

```bash
cd backend
```

### Create a Virtual Environment

```bash
python -m venv venv
```

### Activate the Virtual Environment

- **macOS / Linux:**
  ```bash
  source venv/bin/activate
  ```
- **Windows (Command Prompt):**
  ```cmd
  venv\Scripts\activate
  ```
- **Windows (PowerShell):**
  ```powershell
  venv\Scripts\Activate.ps1
  ```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Configure Environment Variables

The `.env` file in the backend folder contains the default configuration:

```
OLLAMA_MODEL=phi3:mini
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_NUM_CTX=4096
```

You can change the model or context size here if needed.

### Start Ollama

In a **separate terminal**, start the Ollama server:

```bash
ollama serve
```

> On Windows, you can also just open the Ollama app from the Start menu — it starts the server automatically.

### Start the Backend Server

```bash
python run.py
```

The backend will be running at **http://localhost:8282**.

---

## Frontend Setup

Open a **new terminal** and navigate to the frontend folder:

```bash
cd frontend
```

### Install Dependencies

```bash
npm install
```

### Start the Frontend Dev Server

```bash
npm run dev
```

The frontend will be running at **http://localhost:5173**.

---

## Running the Application

You need **three terminals** running simultaneously:

| Terminal | Command         | Purpose                 |
|----------|-----------------|-------------------------|
| 1        | `ollama serve`  | LLM server              |
| 2        | `python run.py` | Backend API (port 8282) |
| 3        | `npm run dev`   | Frontend UI (port 5173) |

Then open **http://localhost:5173** in your browser.

---

## Running Tests

Make sure you are in the `backend` folder with the virtual environment activated:

```bash
cd backend
```

Activate the virtual environment (if not already):

- **macOS / Linux:** `source venv/bin/activate`
- **Windows:** `venv\Scripts\activate`

### Run All Tests

```bash
python -m pytest tests/ -v
```

### Run a Specific Agent's Tests

```bash
python -m pytest tests/test_bug_analyzer.py -v
python -m pytest tests/test_test_case_generator.py -v
python -m pytest tests/test_root_cause_analyzer.py -v
python -m pytest tests/test_bug_report_generator.py -v
```

---

## Project Structure

```
├── backend/
│   ├── agents/                  # Agent implementations
│   │   ├── bug_analyzer.py          # Agent 1 - Bug Analyzer
│   │   ├── test_case_generator.py   # Agent 2 - Test Case Generator
│   │   ├── root_cause_analyzer.py   # Agent 3 - Root Cause Analyzer
│   │   └── bug_report_generator.py  # Agent 4 - Bug Report Generator
│   ├── tools/                   # Custom Python tools
│   │   ├── analysis_tools.py        # Keyword & component extraction
│   │   ├── code_tools.py            # Code validation & formatting
│   │   ├── execution_tools.py       # Pytest execution
│   │   ├── file_tools.py            # File I/O & logging
│   │   └── logging_tools.py         # Structured pipeline logging
│   ├── tests/                   # Test files for each agent
│   ├── api.py                   # FastAPI endpoints
│   ├── graph.py                 # LangGraph pipeline definition
│   ├── state.py                 # Shared agent state (TypedDict)
│   ├── main.py                  # CLI test runner
│   ├── run.py                   # Server entry point
│   ├── requirements.txt         # Python dependencies
│   └── .env                     # Environment configuration
├── frontend/
│   ├── src/                     # React components
│   ├── package.json             # Node dependencies
│   └── vite.config.js           # Vite configuration
└── README.md
```

---

## Troubleshooting

### "Connection refused" error

Ollama is not running. Start it with:

```bash
ollama serve
```

Or open the Ollama app on Windows.

### Model not found

Pull the model first:

```bash
ollama pull phi3:mini
```

### Port already in use

If port 8282 or 5173 is already in use, kill the existing process or change the port:

- Backend: Edit `run.py` and change the port number.
- Frontend: Run `npm run dev -- --port 3000` to use a different port.

### Windows PowerShell script execution error

If you get a script execution policy error when activating the venv:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Then try activating again.