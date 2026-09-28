# Capitolo X: Implementazione Operativa – La Trading Dashboard

L’implementazione di un algoritmo di trading quantitativo, per quanto rigoroso dal punto di vista matematico e statistico, rimane un puro esercizio accademico se non supportato da un'infrastruttura capace di renderlo operativo, monitorabile e trasparente. Per questo motivo, a coronamento del processo di ricerca, è stato sviluppato un intero ecosistema software applicativo: la **Trading Dashboard**. 

L'obiettivo di questo applicativo è duplice: da un lato, tradurre i segnali complessi dei modelli di Machine Learning e Deep Learning in informazioni chiare e fruibili; dall'altro, fornire un ambiente di monitoraggio e simulazione robusto, capace di guidare l'utente nell'analisi critica del comportamento del modello.

## 1. Architettura di Sistema e Filosofia MVC

La progettazione dell'infrastruttura ha seguito una rigorosa separazione delle responsabilità, basandosi sui principi del pattern architetturale **MVC (Model-View-Controller)**, riadattato per le esigenze di una moderna Web Application orientata ai dati.

### 1.1 Model: Gestione Dati e Persistenza
Il livello "Model" rappresenta il cuore dello stato del sistema e della business logic dei dati. È gestito tramite **SQLite**, un database locale leggero ed estremamente affidabile, interrogato attraverso l'ORM **SQLAlchemy**. 
Il sistema non ri-addestra mai i modelli, ma si comporta da *inference engine*. I modelli pre-addestrati (TimesFM, LightGBM, HMM) risiedono in una directory protetta in sola lettura (`/models`). Il Model del database si occupa di mantenere la coerenza dei flussi informativi catturando e storicizzando:
- La **Price Cache**: i prezzi di mercato acquisiti live via Yahoo Finance, aggiornati ogni 2 minuti.
- La **Inference Cache**: i calcoli computazionalmente pesanti (come i forecast di Chronos e TimesFM), salvati per garantire la fluidità dell'interfaccia.
- I **Risultati di Backtest**: le curve di equity generate dinamicamente per ogni combinazione di parametri.

### 1.2 Controller: Motore di Calcolo e API (FastAPI)
Il livello "Controller" è stato implementato utilizzando **FastAPI** (Python 3.10+), un framework ad altissime prestazioni per la creazione di API RESTful. Il Controller funge da ponte vitale tra i modelli AI e il Frontend:
- **Orchestrazione Algoritmica**: implementa rigorosamente la logica dei 5 layer (Direzionalità, Qualità, Regime HMM, Position Sizing e Sigmoid Decay).
- **Scheduler Asincrono (APScheduler)**: gestisce autonomamente il tempo, scaricando i dati macro (Treasury 2Y/10Y, CPI, Consumer Sentiment) tramite API EODHD e innescando la "Weekly Pipeline" ogni venerdì alle 16:05 ET.
- **Prevenzione del Bias**: ricalcola le feature in tempo reale applicando il lag di +1 giorno, garantendo che ogni segnale sia basato solo su informazioni realmente disponibili al momento dell'operazione.

### 1.3 View: L'Interfaccia Utente (Angular)
Il livello "View" è rappresentato dalla dashboard grafica, sviluppata in **Angular 21**. Grazie all'uso intensivo della libreria **Apache ECharts**, il frontend traduce array numerici e probabilità in grafici interattivi e responsivi. L'architettura è stata interamente **Dockerizzata**, permettendo al sistema di essere eseguito agilmente su qualsiasi macchina senza complesse procedure di setup.

---

## 2. L'Esperienza Utente: Strumento Operativo e di Simulazione

L'interfaccia utente è stata studiata per trasformare una "black-box" algoritmica in un "libro aperto" interattivo. Per un gestore di portafoglio o un analista, la dashboard non è solo un monitor, ma un laboratorio di analisi dinamica.

### 2.1 Navigazione Storica e "Viaggio nel Tempo"
Una delle funzionalità più potenti della dashboard è la capacità di **ispezione granulare settimana per settimana**. Attraverso appositi dropdown temporali presenti nei pannelli dei Segnali, delle Bande Chronos e dell'Allocazione, l'utente può "viaggiare indietro nel tempo" a qualsiasi venerdì del passato.
- **Utilità**: Questo permette di analizzare esattamente *perché* il modello ha preso una determinata decisione in un momento di mercato specifico (ad esempio durante un crollo improvviso), verificando quali ratio fossero attivi, quale fosse la Bet Quality e come le bande di incertezza si stessero allargando o stringendo.

### 2.2 What-If Analysis e Comparazione Equity Curve
Il sistema eleva il concetto di backtest da report statico a **simulazione dinamica**. Attraverso la *Interactive Sidebar*, l'utente può manipolare in tempo reale i parametri di governance:
- **Sperimentazione**: Cambiando la soglia di Bet Quality o i moltiplicatori di Stop Loss, il backend ricalcola istantaneamente l'intera serie storica.
- **Visualizzazione Tripla**: La Equity Curve plotta simultaneamente tre linee:
    1. **S&P 500 (Benchmark)**: Il riferimento di mercato passivo.
    2. **Algoritmo Originale**: La performance basata sui parametri ottimizzati nella tesi.
    3. **Parametri Interattivi (Linea Blu)**: Il risultato degli "improvvisati" cambiamenti dell'utente.
- **Valore aggiunto**: Questo permette di valutare immediatamente la sensibilità del modello e la robustezza dei parametri scelti, scoprendo potenziali miglioramenti o testando scenari di stress personalizzati.

### 2.3 Risk Management Attivo e Trasparenza
- **Matrice di Correlazione Interattiva**: L'utente può visualizzare i legami tra i 26 ETF su diversi orizzonti (da 1 settimana a 1 anno). Identificare aree di "iper-correlazione" (segnalate in rosso) permette di capire istantaneamente perché il **Sigmoid Decay** stia tagliando l'esposizione, proteggendo il portafoglio da rischi di concentrazione sistemica.
- **Weekly Decomposition & Trigger**: Il diagramma scompone il rendimento settimanale evidenziando se un ETF è stato chiuso per scadenza naturale del venerdì o se ha colpito un livello di *Take Profit* o *Stop Loss* durante la settimana. Questa trasparenza elimina ogni ambiguità sulla resa operativa.

### 2.4 Supporto Decisionale e Glossario
- **Glossario ETF Integrato**: L'universo di 30 ETF è mappato in un glossario hover-active. Passando il mouse sui ticker, l'utente visualizza nome completo, descrizione e principali componenti sottostanti.
- **Utilità**: Questo assicura che anche un utente meno esperto di strumenti americani possa avere una comprensione immediata di *cosa* sta effettivamente acquistando l'algoritmo, migliorando il controllo e la consapevolezza operativa.

---

## 3. Disponibilità e Reperibilità del Codice

L’intero ecosistema software è stato reso pubblico per garantire la massima riproducibilità. L'infrastruttura abbraccia pienamente i concetti di Containerization.

Il codice sorgente dell'applicativo è versionato su **GitHub**:
- **Repository**: [https://github.com/SerGOLD02/msc-algo-trading-system.git](https://github.com/SerGOLD02/msc-algo-trading-system.git)

Le immagini Docker pre-compilate sono ospitate su **Docker Hub**:
- **Immagine Backend**: `sergiogolino/msc-algo-trading-backend:latest`
- **Immagine Frontend**: `sergiogolino/msc-algo-trading-frontend:latest`

Per garantire la massima trasparenza accademica e la piena riproducibilità tecnica dei risultati esposti nella tesi, il repository GitHub è stato organizzato secondo una struttura modulare che separa nettamente la fase di **ricerca quantitativa (R&D)** dalla fase di **implementazione operativa (Produzione)**. Un esaminatore può navigare tra i seguenti componenti chiave:

### 3.1 Il Nucleo della Ricerca: Directory `TESI DATI PULITI`
Questa cartella costituisce il fondamento scientifico del progetto. Al suo interno si trovano:
- **Jupyter Notebooks Master**: Il file `TESI_DATI_PULITI_FINALE.ipynb` contiene l'intero workflow di ricerca: dalla pulizia dei dati Bloomberg originali al feature engineering, fino all'addestramento e alla validazione dei modelli. Per una consultazione internazionale, è disponibile la versione tradotta integralmente in inglese: `THESIS_CLEAN_DATA_FINAL.ipynb`.
- **Dataset e Modelli (`/Dataset`)**: Contiene i file `.parquet` pronti per l'inferenza, i pesi storici dell'HRP, le labels del Triple Barrier Method e i modelli serializzati in formato `.pkl` (LightGBM, HMM) e `.json` (XGBoost). Questo permette di replicare l'inferenza senza dover ripetere l'intera fase di training.
- **Analisi Statistica e Bias Check (`/CHECK_ANTI_BIAS_RESULTS`)**: Una raccolta esaustiva di file CSV e report (SHAP values, test di perturbazione, analisi di stabilità delle feature) che documentano la resistenza del modello a bias cognitivi e tecnici (come il look-ahead bias).
- **Visualizzazioni e Grafici (`/PLOTS`)**: Tutti i grafici generati durante la fase di training e validazione, esportati in alta risoluzione per un'ispezione visiva immediata delle metriche di performance.

### 3.2 Ambiente Tecnico e Riproducibilità
Per eliminare l'annoso problema del "funziona solo sulla mia macchina", il repository include strumenti di automazione per il setup:
- **Configurazioni di Ambiente**: I file `requirements.txt` (sia nella root che nelle sottocartelle) elencano con precisione le versioni di tutte le librerie Python utilizzate (FastAPI, PyTorch, LightGBM, scikit-learn, ecc.), consentendo la creazione istantanea di ambienti virtuali coerenti.
- **Script di Automazione**: Script come `start_gemini.ps1` facilitano l'avvio rapido di sottosistemi di analisi, mentre il file `docker-compose.yml` orchestra l'intera infrastruttura con un singolo comando.

### 3.3 Codice Sorgente della Dashboard: Directory `trading_dashboard`
Contiene l'implementazione software completa presentata in questo capitolo, suddivisa in:
- **Backend**: Logica in Python/FastAPI organizzata in moduli (analytics, backtest, hmm, inference, market_data, meta_labeler, etc.), che implementa i 5 layer decisionali.
- **Frontend**: Sorgenti Angular 21 (TypeScript), comprensivi di componenti standalone, servizi per la comunicazione API, pipeline di internazionalizzazione (i18n) e configurazioni Nginx per il serving in produzione.
- **Persistenza**: Definizioni dei modelli SQLAlchemy e istanza del database SQLite `trading.db` per la cache dei dati storici e delle inferenze.

### 3.4 Documentazione e Guide
Il repository è corredato da file di guida dettagliati:
- **`CONTESTO.md`**: Spiega la filosofia dell'algoritmo e le regole critiche di implementazione.
- **`GEMINI.md`**: Una guida tecnica completa per la replica esatta dell'ambiente e dei file modello.
- **`README.md`**: Fornisce le istruzioni "Quick Start" per avviare l'intero sistema in meno di 5 minuti tramite Docker.

In sintesi, questa infrastruttura non si limita a eseguire un algoritmo, ma fornisce un ambiente completo per l'ispezione, la validazione e la simulazione critica, rendendo l'adozione di questa strategia quantitativa un processo guidato dai dati e dalla trasparenza.

---

## 4. Mappatura Tecnica delle Risorse

### 4.1 Albero della Repository GitHub
La struttura del codice è organizzata per massimizzare la separazione tra logica di ricerca e applicativo web:

```text
msc-algo-trading-system/
├── TESI DATI PULITI/                # Core della ricerca (R&D)
│   ├── Dataset/                     # Modelli (.pkl, .json) e dati (.parquet)
│   ├── CHECK_ANTI_BIAS_RESULTS/     # Report di validazione statistica
│   ├── PLOTS/                       # Visualizzazioni prodotte in training
│   ├── TESI_DATI_PULITI_FINALE.ipynb# Notebook master (Italiano)
│   └── THESIS_CLEAN_DATA_FINAL.ipynb# Notebook master (Inglese)
├── trading_dashboard/               # Implementazione Software
│   ├── backend/                     # API FastAPI (Python)
│   │   ├── modules/                 # Logica decisionale (5 layer)
│   │   ├── database/                # Persistenza SQLite e SQLAlchemy
│   │   └── Dockerfile               # Immagine Backend
│   ├── frontend/                    # UI Angular 21 (TypeScript)
│   │   ├── src/app/shared/          # Componenti grafici (ECharts)
│   │   └── Dockerfile               # Immagine Frontend (Nginx)
│   └── docker-compose.yml           # Orchestrazione multi-container
├── .env                             # Configurazioni di sistema
└── RELAZIONE.md                     # Questo documento
```

### 4.2 Organizzazione Repository Docker
L'ecosistema è distribuito tramite due immagini speculari sul registry Docker Hub, garantendo l'isolamento dei processi:

```text
docker.io/sergiogolino/
├── msc-algo-trading-backend:latest  # Container Logica & AI
│   └── (FastAPI + PyTorch + LightGBM + HMM)
└── msc-algo-trading-frontend:latest # Container Interfaccia
    └── (Angular 21 + Nginx + i18n)
```

---

## 5. Inventario dei Dataset e Artefatti di Ricerca

L'intero ecosistema della Trading Dashboard è alimentato da una serie di dataset, modelli e file di diagnostica generati durante la fase di ricerca. Per garantire la piena riproducibilità e trasparenza, tali artefatti sono suddivisi per logica operativa all'interno del repository.

### 5.1 Dati Sorgente e Ingestione (Pre-Processing)
Questi file rappresentano il punto di partenza: il dato "grezzo" acquisito dai terminali professionali e normalizzato per l'analisi.
- **`DATI BLOOMBERG COMPLETI.xlsx`**: Costituisce il dataset primario. Contiene le serie storiche dei prezzi degli ETF scaricati dal terminale Bloomberg, già rettificati per dividendi e operazioni societarie. È la "ground truth" per il calcolo delle equity line.
- **`dati_originali_con_nan.xlsx`**: Generato dalla prima fase di pulizia, questo file normalizza il calendario Bloomberg e mappa i giorni di chiusura (Volume_Intensity, Is_Half_Day), mantenendo i NaN strutturali per prevenire ogni forma di *Look-Ahead Bias*.
- **`DATASET_INFERENCE_READY.parquet`**: Il dataset "madre" per il Machine Learning. Contiene i Log-Ratios normalizzati (Rolling Z-Score a 252 giorni) e la totalità delle 174 feature tecniche utilizzate (Momentum, Volatilità, EMA, Cross-Sectional Momentum, ecc.).

### 5.2 Moduli Algoritmici e Sub-Systems
Risultati intermedi salvati in formato Parquet per consentire un'architettura modulare ed evitare ricalcoli ridondanti:
- **`TRIPLE_BARRIER_LABELS_OPTIMAL.parquet`**: Il dataset dei target. Contiene l'etichettatura binaria generata dal *Triple Barrier Method*, che indica se un segnale ha raggiunto il target di profitto, lo stop loss o il limite temporale.
- **`HMM_REGIMES.parquet`**: L'output del classificatore di stati. Fornisce la mappatura storica dei regimi di mercato (0-4), identificando le finestre temporali in cui è stato attivato il *Crisis State*.
- **`HRP_WEIGHTS.parquet`**: Il log dei pesi calcolati tramite *Hierarchical Risk Parity*. Memorizza l'allocazione dinamica del portafoglio, con i vincoli di cap al 15% applicati tramite l'algoritmo di Waterfilling.
- **`SIGMOID_DECAY.parquet`**: Archivio storico del fattore di riduzione dell'esposizione, calcolato sulla base della correlazione media dell'universo ETF a 52 settimane.

### 5.3 Foundation Models e Cache Live
Gestiscono le predizioni generate dai modelli di Deep Learning e l'operatività in tempo reale:
- **`INFERENZE_FULL_DATASET_O2TFM.parquet`**: Il database complessivo delle predizioni. Include i risultati del forecasting direzionale di *Google TimesFM* e le stime di incertezza di *Amazon Chronos* calcolate su tutto lo storico.
- **`FM_LIVE_CACHE.parquet`**: Utilizzato dal motore live per memorizzare le inferenze più recenti recuperate via YFinance, rendendo l'esecuzione della pipeline settimanale istantanea per l'utente finale.

### 5.4 Modelli Serializzati e Parametrizzazione
I "cervelli" del sistema salvati in formato binario o JSON:
- **`HMM_MODEL.pkl`**: Il modello *Hidden Markov* addestrato. Viene caricato dal modulo live per dedurre il regime attuale basandosi sui dati di volatilità di SPY, TLT e VIX.
- **`LGB_FINAL_MODEL.pkl`**: Il classificatore LightGBM finale che agisce da Meta-Labeler per filtrare i segnali in base alla loro qualità.
- **`BEST_PARAMS_LGB.json`**: Raccolta degli iperparametri ottimali (learning rate, depth, estimators) estratti tramite ottimizzazione Bayesiana (Optuna).

### 5.5 Diagnostica ed Explainability (`/CHECK_ANTI_BIAS_RESULTS`)
Tutto il set di file CSV utilizzati per l'analisi critica contenuta nel **Capitolo 13** della tesi, essenziali per dimostrare l'assenza di bias:
- **`13_1_shap_global_importanza.csv`**: Classifica delle feature basata sui valori SHAP medi.
- **`13_2_perturbation_results.csv`**: Analisi dell'impatto sulla Bet Quality in caso di disattivazione dei Foundation Models.
- **`13_3_hmm_statistiche_regimi.csv`**: Rendimenti e Win Rate spacchettati per ogni stato del mercato.
- **`13_6_ratio_directional_accuracy.csv`**: Analisi dell'*Hit Rate* direzionale su ogni singolo spread di ETF.
