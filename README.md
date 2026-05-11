# MSc Algorithmic Trading System
### Weekly ETF Rotation Strategy with Foundation Models, LightGBM Meta-Labeling and HMM Regime Detection

> **Master's Thesis** — Sergio Golino  
> MSc in Data Science and Management — LUISS Guido Carli, Rome  
> Academic Year 2025/2026

---

## 📊 Dashboard Preview

<!-- Add a screenshot of the dashboard here -->
![Dashboard Preview](docs/screenshot_dashboard.png)

<!-- Add a screenshot of the equity curve here -->
![Equity Curve](docs/screenshot_equity.png)

---

## 🏗️ System Architecture

The system is composed of **5 algorithmic layers** operating in sequence every operational Friday:

| Layer | Component | Function |
|-------|-----------|----------|
| 1 | **TimesFM** (Google, 200M params) | Directional forecasting on 20 relative strength ratios |
| 2 | **LightGBM Meta-Labeler** | Signal quality filter (Bet_Quality score) |
| 3 | **HMM Regime Detection** | Market crisis detection and Crisis Basket activation |
| 4 | **HRP Position Sizing** | Hierarchical Risk Parity portfolio weight optimization |
| 5 | **Sigmoid Decay** | Exposure reduction during high-correlation market phases |

### Investment Universe
- **26 US ETFs** covered by 20 relative strength ratios
- **4 defensive ETFs** (Crisis Basket: SH, PSQ, RWM, VIXY)
- Bloomberg dataset 2004–2025, weekly frequency (Fridays)

### Out-of-Sample Results (Test Set 2023–2025)

| Metric | System | EW Benchmark | SPY B&H |
|--------|--------|-------------|---------|
| CAGR | **15.79%** | 14.20% | ~22% |
| Max Drawdown | **-5.67%** | -9.55% | -16.88% |
| Sharpe Ratio | **2.247** | 1.328 | 1.411 |
| Calmar Ratio | **2.782** | 1.486 | 1.234 |

---

## 🚀 Quick Start (Docker)

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- Git installed
- At least 8GB of available RAM

### 1. Clone the repository

```bash
git clone https://github.com/SerGOLD02/msc-algo-trading-system.git
cd msc-algo-trading-system
```

### 2. Start with Docker Compose

```bash
cd trading_dashboard
docker-compose up
```

The first run takes **15–20 minutes** to download and build the images.

### 3. Open the dashboard

| Service | URL |
|---------|-----|
| Angular Dashboard | http://localhost:4200 |
| Backend API | http://localhost:8000 |
| API Documentation | http://localhost:8000/docs |
| Health Check | http://localhost:8000/health |

---

## 🐳 Docker Hub (Pre-built Images)

To skip the local build, pull the pre-built images directly:

```bash
docker pull sergiogolino/msc-algo-trading-backend:latest
docker pull sergiogolino/msc-algo-trading-frontend:latest
```

Then start with:

```bash
cd trading_dashboard
docker-compose up
```

---

## 🤖 Foundation Models (Optional GPU)

The system supports two operational modes:

**CPU Mode (default)** — Uses pre-computed historical averages as a fallback for TimesFM and Chronos. Works on any machine without a GPU.

**GPU Mode** — Runs TimesFM and Chronos in real time. Requires an NVIDIA GPU with compatible drivers.

```bash
# Start with GPU support (requires NVIDIA Docker runtime)
docker-compose --profile gpu up
```

Foundation Models are automatically downloaded from HuggingFace on the first GPU run (~4GB). Subsequent inferences are cached locally to avoid recomputation.

---

## 📁 Project Structure

```
msc-algo-trading-system/
├── TESI DATI PULITI/
│   ├── Dataset/                          # Pre-trained models and datasets
│   │   ├── LGB_FINAL_MODEL.pkl           # Final LightGBM classifier
│   │   ├── HMM_MODEL.pkl                 # HMM for regime detection
│   │   ├── HRP_WEIGHTS.parquet           # Pre-computed HRP weights
│   │   ├── SIGMOID_DECAY.parquet         # Sigmoid Decay multipliers
│   │   ├── INFERENZE_FULL_*.parquet      # Foundation Models inferences
│   │   ├── BEST_PARAMS_LGB.json          # Optimized LightGBM hyperparameters
│   │   └── FM_FALLBACK_MEANS.json        # CPU fallback for Foundation Models
│   └── TESI_DATI_PULITI_FINALE.ipynb     # Complete research notebook
└── trading_dashboard/
    ├── docker-compose.yml                # Container orchestration
    ├── backend/                          # FastAPI Python backend
    │   ├── Dockerfile
    │   ├── main.py
    │   ├── config.py
    │   └── modules/
    │       ├── signals/                  # Live operational engine (yfinance)
    │       ├── backtest/                 # Historical backtest engine
    │       ├── hmm/                      # Regime detection
    │       ├── hrp/                      # Position sizing
    │       ├── inference/                # Foundation Models integration
    │       └── analytics/                # KPIs and metrics
    └── frontend/                         # Angular 21 dashboard
        ├── Dockerfile
        └── src/
```

---

## 🔬 Jupyter Notebook

The complete research notebook is available at `TESI DATI PULITI/TESI_DATI_PULITI_FINALE.ipynb`.

It covers all project phases: Bloomberg data cleaning, feature engineering, Foundation Models tournament, Triple Barrier Method, LightGBM optimization with Optuna, HMM, HRP, Sigmoid Decay, Ablation Study, Walk-Forward Analysis, Monte Carlo Stress Test, and the live execution module with yfinance.

To run it, upload the notebook and the Dataset folder to Google Drive and open it in Google Colab.

---

## 🛠️ Technology Stack

**Machine Learning & Finance**
- `lightgbm` — Meta-labeler classifier
- `timesfm` — Google Foundation Model for time series forecasting
- `chronos-forecasting` — Amazon Foundation Model for epistemic uncertainty
- `hmmlearn` — Hidden Markov Model for regime detection
- `scipy` / `scikit-learn` — ML utilities
- `yfinance` — Real-time market data

**Backend**
- `FastAPI` + `uvicorn` — REST API
- `SQLAlchemy` + `SQLite` — Data persistence
- `APScheduler` — Periodic tasks (price refresh, Friday pipeline)

**Frontend**
- `Angular 21` — SPA framework
- `ngx-echarts` — Interactive charts
- `Nginx` — Static serving and reverse proxy

**Infrastructure**
- `Docker` + `Docker Compose` — Containerization
- `GitHub` — Version control

---

## 📄 Citation

If you use this work in your research:

```bibtex
@mastersthesis{golino2026algo,
  author  = {Sergio Golino},
  title   = {Weekly Algorithmic Trading System with Foundation Models and Meta-Labeling},
  school  = {LUISS Guido Carli},
  year    = {2026},
  note    = {https://github.com/SerGOLD02/msc-algo-trading-system}
}
```

---

## 📬 Contact

**Sergio Golino** — [@SerGOLD02](https://github.com/SerGOLD02)

---

*Developed as a Master's thesis project. Bloomberg data used for training is proprietary and not included in this repository.*
