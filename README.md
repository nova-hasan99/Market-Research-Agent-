# MarketLens

An AI-powered multi-timeframe market research platform for real-time technical analysis of Forex pairs and stocks. Get actionable insights, AI summaries, and trading levels in seconds.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

## Features

- **Multi-Timeframe Analysis**: Analyze 1m, 5m, 15m, 1H, 4H, 8H, 1D, 1W, 1M candle charts
- **Technical Indicators**: RSI, StochRSI, MACD, Ichimoku, ATR, Fibonacci, Volume/OBV
- **Candlestick Patterns**: Hammer, Shooting Star, Doji, Engulfing, Spinning Top, Marubozu
- **AI Summaries**: Multi-LLM support (Gemini, Groq, OpenAI, Anthropic) with fallback rule-based analysis
- **Trade Levels**: Automatic entry, stop-loss, and take-profit calculation
- **Market Sentiment**: News sentiment, retail positioning, COT data
- **User Dashboard**: Save and export analyses, compare multiple pairs
- **Super Admin Panel**: User management, API status, system configuration
- **Forex Pair Normalization**: Automatic inverse pair handling (USD/EUR to EUR/USD conversion)
- **Multi-Language Support**: English, Bangla context-aware responses

## Tech Stack

- **Backend**: FastAPI 0.100+, Python 3.10+
- **Database**: Supabase (PostgreSQL)
- **Authentication**: Supabase Auth with JWT tokens
- **Frontend**: HTML5, CSS3, Vanilla JavaScript
- **Data Providers**: TwelveData, AlphaVantage, Yahoo Finance, Polygon, Finnhub, NewsAPI
- **Deployment**: Render, Docker-ready

## Project Structure

```
MarketLens/
  app/
    __init__.py
    config.py              # Environment configuration
    auth.py                # Authentication & JWT handling
    db.py                  # Supabase client setup
    routes.py              # Analysis endpoints (forex & stocks)
    routes_auth.py         # Login, register, password reset
    routes_dashboard.py    # Dashboard, admin panel, user management
    models.py              # Request/response Pydantic models
    analysis.py            # Alignment scoring, trade level calculation
    indicators.py          # Technical indicator calculations (RSI, MACD, etc)
    patterns.py            # Candlestick pattern detection
    timeframes.py          # Timeframe mapping & metadata
    ai.py                  # AI summary generation
    deps.py                # Dependency injection
    providers/             # Data provider modules
      price.py             # OHLCV data fetching
      sentiment.py         # News sentiment scoring
      correlation.py       # Pair correlation & retail sentiment
      calendar.py          # Economic event calendar
      cot.py               # CFTC COT data
      yields.py            # Bond yield differential
      stock_info.py        # Fundamental & analyst data
      intermarket.py       # USD strength index
  static/
    css/
      style.css            # Global styles, design system
      dashboard.css        # Dashboard & admin panel styles
    js/
      app.js               # Research page logic
      dashboard.js         # Dashboard & admin management
  templates/
    index.html             # Landing page
    research.html          # Analysis form page
    dashboard.html         # User analysis history
    admin_users.html       # Super admin user management
    admin_api_status.html  # API provider status
    login.html             # Login page
    register.html          # Account creation
    forgot_password.html   # Password reset request
    reset_password.html    # Password reset form
  main.py                  # FastAPI app entry point
  requirements.txt         # Python dependencies
  .env.example             # Environment template (see below)
  README.md                # This file
```

## Quick Start

### Prerequisites

- Python 3.10 or higher
- pip or poetry
- A Supabase account (free tier available)
- Browser with JavaScript enabled

### Installation

1. Clone the repository:
```bash
git clone https://github.com/nova-hasan99/MarketLens.git
cd MarketLens
```

2. Create a virtual environment:
```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/Mac:
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

### Environment Setup

Copy the example file:
```bash
cp .env.example .env
```

Edit `.env` and fill in all required and optional keys (see table below).

#### Environment Variables Reference

**REQUIRED for Basic Operation**

| Variable | Purpose | Example | How to Get |
|----------|---------|---------|-----------|
| VITE_SUPABASE_URL | Supabase project URL | https://abc123.supabase.co | Create account at https://supabase.com |
| VITE_SUPABASE_ANON_KEY | Supabase public key | eyJhbGc... | In Supabase: Settings > API > anon key |
| SUPABASE_SERVICE_KEY | Supabase service role (admin) | eyJhbGc... (longer) | In Supabase: Settings > API > service_role key |
| SUPABASE_ACCESS_TOKEN | Supabase Management API token | sbp_abc123... | In Supabase: Settings > Access Tokens |
| VITE_ADMIN_EMAIL | First admin email for setup | admin@example.com | Your email address |
| VITE_ADMIN_PASSWORD | First admin password | StrongP@ss123 | Create a strong password |

**OPTIONAL for Price Data** (at least ONE required)

| Variable | Purpose | Free Tier | How to Get |
|----------|---------|-----------|-----------|
| TWELVE_DATA_KEY | Primary OHLCV provider | Yes (800 req/day) | https://twelvedata.com/pricing |
| ALPHA_VANTAGE_KEY | Fallback OHLCV & fundamentals | Yes (5 req/min) | https://www.alphavantage.co/support/#api-key |
| POLYGON_KEY | Stocks data | Yes (limited) | https://polygon.io |
| FINNHUB_KEY | Economic calendar & fundamentals | Yes (60 req/min) | https://finnhub.io |

**OPTIONAL for AI Summaries** (at least ONE recommended, else rule-based fallback)

| Variable | Purpose | Free Tier | How to Get |
|----------|---------|-----------|-----------|
| GEMINI_API_KEY | Google's LLM (primary) | Yes (60 req/min) | https://aistudio.google.com/app/apikeys |
| GROQ_API_KEY | Fast open-source LLM | Yes | https://console.groq.com/keys |
| OPENAI_API_KEY | ChatGPT 4o | Paid | https://platform.openai.com/api-keys |
| ANTHROPIC_API_KEY | Claude models | Paid | https://console.anthropic.com/keys |

**OPTIONAL for News & Sentiment**

| Variable | Purpose | Free Tier | How to Get |
|----------|---------|-----------|-----------|
| NEWSAPI_KEY | News sentiment | Yes (100 req/day) | https://newsapi.org |
| OANDA_API_KEY | Retail trader positioning | Yes (demo account) | https://www.oanda.com/register |
| IG_API_KEY | Alternative retail sentiment | No | https://www.ig.com |
| TRADINGECONOMICS_KEY | Macro economic data | Paid | https://tradingeconomics.com/api |

**OPTIONAL for Email Features** (welcome emails, password reset)

| Variable | Purpose | Default | How to Set |
|----------|---------|---------|-----------|
| SMTP_HOST | Email server address | Leave blank | For Gmail: smtp.gmail.com |
| SMTP_PORT | Email server port | 587 | TLS port: 587 |
| SMTP_USER | Email account username | Leave blank | Your Gmail address |
| SMTP_PASSWORD | Email account password | Leave blank | Gmail App Password (not regular password) |
| SMTP_FROM | Sender email display | Leave blank | "MarketLens <noreply@yourdomain.com>" |
| SITE_URL | Public site URL | http://localhost:8000 | Your domain: https://example.com |

**Gmail Setup for Email**

1. Enable 2-Step Verification: https://myaccount.google.com/security
2. Generate App Password: https://myaccount.google.com/apppasswords
3. Set these in .env:
```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-gmail@gmail.com
SMTP_PASSWORD=<16-char app password from step 2>
SMTP_FROM="MarketLens <your-gmail@gmail.com>"
```

**Server Configuration**

| Variable | Purpose | Default |
|----------|---------|---------|
| PORT | Server port | 8000 |

### Database Setup

Initialize the Supabase database:

```bash
python scripts/setup_db.py
```

This creates all necessary tables:
- users (via Supabase Auth)
- profiles (user metadata)
- analyses (saved analysis results)
- settings (user preferences)

### Running the Application

Start the development server:

```bash
uvicorn main:app --reload
```

Server will start at: http://localhost:8000

Open your browser and navigate to:
- **Home**: http://localhost:8000
- **Research**: http://localhost:8000/research (login required)
- **Dashboard**: http://localhost:8000/dashboard (login required)
- **Admin Panel**: http://localhost:8000/admin/users (admin only)
- **API Status**: http://localhost:8000/admin/api-status (admin only)

## API Endpoints

### Public Endpoints

- `GET /` Landing page
- `POST /login` User login
- `POST /register` New account registration
- `POST /forgot-password` Password reset request
- `POST /reset-password` Password reset confirmation
- `GET /logout` Sign out

### Authenticated Endpoints

- `GET /research` Analysis form page
- `POST /api/analyze` Execute analysis (Forex/Stock)
- `GET /api/search-stock` Stock ticker search
- `GET /dashboard` User analysis history
- `GET /dashboard/view/{id}` Full-page analysis viewer
- `GET /api/preferences` User settings
- `POST /api/dashboard/analyses/{id}` View saved analysis
- `DELETE /api/dashboard/analyses/{id}` Delete analysis

### Admin Only Endpoints

- `GET /admin/users` User management page
- `GET /admin/api-status` Provider status dashboard
- `GET /api/admin/users` List all users
- `POST /api/admin/users/{uid}/deactivate` Suspend user
- `POST /api/admin/users/{uid}/activate` Reactivate user
- `DELETE /api/admin/users/{uid}` Permanently delete user
- `GET /api/admin/users/{uid}/analyses` View user analyses

## Analysis Features

### Forex Analysis

Submit a currency pair with timeframe:
```json
{
  "asset_type": "forex",
  "symbol": "EUR",
  "quote": "USD",
  "timeframe": "1H"
}
```

Response includes:
- Alignment score (0-113)
- Bias direction (Bullish/Bearish/Unclear)
- RSI, MACD, Ichimoku signals
- Candlestick patterns
- Trade levels (entry, SL, TP1, TP2)
- AI summary with reasoning
- News sentiment
- Key risk factors

### Stock Analysis

Submit a ticker symbol:
```json
{
  "asset_type": "stock",
  "symbol": "AAPL",
  "timeframe": "1D"
}
```

Response includes:
- Technical indicators
- Fundamental data (P/E, dividend, etc)
- Earnings history
- Analyst consensus
- Insider trading activity
- Short interest & institutional ownership
- Sector performance

## User Roles

### Regular User

- Access research and analysis tools
- Save analyses to dashboard
- Export analysis results
- View personal analysis history
- Change password

### Super Admin

- View all registered users
- Suspend/activate user accounts
- Permanently delete users and their data
- View API provider status
- Monitor system health

## Configuration & Customization

### Timeframe Guide

The system automatically shows trading guidance for each timeframe:
- 1m, 5m: Scalping, high frequency
- 15m: Short-term intraday
- 1H, 4H: Intraday swing
- 8H: Short swing
- 1D: Swing trade
- 1W, 1M: Position trade

### Alignment Score

Composite metric (0-113 for Forex, 0-100 for stocks):
- 80+: Strong signal
- 60-80: Good signal
- 40-60: Mixed signals
- Below 40: Weak signal

Components:
- Technical indicators (40%)
- Pattern recognition (30%)
- Volume analysis (15%)
- Risk metrics (15%)

### Risk Management

System enforces:
- Minimum 1.5:1 risk-reward ratio
- Stop loss below key support
- Position sizing guidance
- Drawdown warnings

## Development

### Code Structure

- **routes.py**: Main analysis endpoints
- **indicators.py**: Technical analysis calculations
- **patterns.py**: Candlestick pattern detection
- **analysis.py**: Scoring and trade level logic
- **providers/**: External data integration
- **auth.py**: Authentication and JWT
- **db.py**: Database operations

### Adding a New Data Provider

1. Create file in `app/providers/new_provider.py`
2. Implement fetch function
3. Add error handling and fallback
4. Import in `routes.py`
5. Integrate into analysis pipeline

### Testing

Run tests:
```bash
pytest tests/
```

Run with coverage:
```bash
pytest --cov=app tests/
```

## Deployment

### Docker

Build image:
```bash
docker build -t marketlens .
```

Run container:
```bash
docker run -p 8000:8000 --env-file .env marketlens
```

### Render.com

1. Push repository to GitHub
2. Connect to Render
3. Set environment variables in Render dashboard
4. Deploy

### Production Checklist

- [ ] Set SITE_URL to your domain
- [ ] Enable HTTPS (set secure=True in auth.py)
- [ ] Configure SMTP for emails
- [ ] Set strong admin password
- [ ] Enable database backups
- [ ] Configure rate limiting
- [ ] Monitor API usage
- [ ] Set up error logging
- [ ] Enable CORS for frontend domain

## Troubleshooting

### Common Issues

**"NameError: name 'SUPABASE_URL' is not defined"**
- Solution: Ensure all required .env variables are set
- Run: `python -c "from app.config import *; print('Config OK')"`

**"Failed to fetch OHLCV data"**
- Check API key validity
- Verify rate limits not exceeded
- Ensure symbol format is correct (EUR/USD for forex)
- Check internet connection

**"User can't log in"**
- Verify email exists in Supabase Auth
- Check if account is deactivated
- Clear browser cookies
- Try password reset

**"Admin panel shows no users"**
- Check user has is_admin=true in profiles table
- Or add email to VITE_ADMIN_EMAIL env var
- Verify Supabase connection

### Debug Mode

Enable verbose logging:
```bash
export DEBUG=1
uvicorn main:app --reload --log-level debug
```

### Database Issues

Reset database (WARNING: deletes all data):
```bash
python scripts/setup_db.py --reset
```

## Performance

- Analysis calculation: 200-500ms depending on data providers
- Cached responses: ~50ms
- Real-time streaming: Not currently supported
- Concurrent users: Tested up to 100 simultaneous

## Security

- JWT tokens expire in 7 days (access) and 30 days (refresh)
- Passwords hashed via Supabase Auth
- API keys stored server-side only
- CORS enabled for frontend domain
- Rate limiting on analysis endpoint
- SQL injection protected via Supabase RLS
- XSS prevention via HTML escaping

## Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/your-feature`
3. Commit changes: `git commit -m "Add your feature"`
4. Push to branch: `git push origin feature/your-feature`
5. Open pull request

## License

MIT License. See LICENSE file for details.

## Roadmap

- [ ] Real-time WebSocket streaming
- [ ] Advanced backtesting engine
- [ ] Mobile app (React Native)
- [ ] Advanced charting (TradingView integration)
- [ ] Machine learning models
- [ ] Portfolio management
- [ ] Discord/Telegram alerts
- [ ] API documentation (OpenAPI/Swagger)

## Authors

Created by Hasan for MarketLens trading analysis platform.

## Acknowledgments

- Supabase for authentication and database
- TwelveData, AlphaVantage for market data
- FastAPI community
- Anthropic Claude for AI summaries
