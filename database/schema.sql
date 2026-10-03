CREATE TABLE instruments (
    instrument_id   VARCHAR(20) PRIMARY KEY,
    isin            CHAR(12) UNIQUE NOT NULL,
    ticker          VARCHAR(20) NOT NULL,
    instrument_name VARCHAR(200) NOT NULL,
    asset_type      VARCHAR(30) NOT NULL,
    currency        CHAR(3) NOT NULL
);
 
CREATE TABLE counterparties (
    counterparty_id   VARCHAR(20) PRIMARY KEY,
    counterparty_name VARCHAR(200) NOT NULL,
    country           CHAR(2) NOT NULL,
    counterparty_type VARCHAR(50) NOT NULL
);
 
CREATE TABLE trades (
    trade_id            VARCHAR(30) PRIMARY KEY,
    instrument_id       VARCHAR(20) NOT NULL REFERENCES instruments(instrument_id),
    counterparty_id     VARCHAR(20) NOT NULL REFERENCES counterparties(counterparty_id),
    side                VARCHAR(4)  NOT NULL CHECK (side IN ('BUY','SELL')),
    quantity            NUMERIC(20,4) NOT NULL CHECK (quantity > 0),
    price               NUMERIC(20,6) NOT NULL CHECK (price > 0),
    trade_value         NUMERIC(24,2) GENERATED ALWAYS AS (quantity * price) STORED,
    trade_currency      CHAR(3) NOT NULL,
    trade_datetime      TIMESTAMP NOT NULL,
    settlement_date     DATE NOT NULL,
    confirmation_status VARCHAR(30) NOT NULL,
    matching_status     VARCHAR(30) NOT NULL
);
 
CREATE TABLE settlement_status (
    trade_id              VARCHAR(30) PRIMARY KEY REFERENCES trades(trade_id),
    cash_required         NUMERIC(20,2) NOT NULL,
    cash_available        NUMERIC(20,2) NOT NULL,
    securities_required   NUMERIC(20,4) NOT NULL,
    securities_available  NUMERIC(20,4) NOT NULL,
    instruction_status    VARCHAR(30) NOT NULL,
    reconciliation_status VARCHAR(30) NOT NULL,
    settlement_status     VARCHAR(40) NOT NULL,
    primary_reason        VARCHAR(60)
);
 
CREATE TABLE settlement_events (
    event_id        BIGSERIAL PRIMARY KEY,
    trade_id        VARCHAR(30) NOT NULL REFERENCES trades(trade_id),
    event_type      VARCHAR(50) NOT NULL,
    event_timestamp TIMESTAMP NOT NULL,
    event_status    VARCHAR(30) NOT NULL
);
 
CREATE TABLE exceptions (
    exception_id      BIGSERIAL PRIMARY KEY,
    trade_id          VARCHAR(30) NOT NULL REFERENCES trades(trade_id),
    exception_type    VARCHAR(60) NOT NULL,
    severity          VARCHAR(20) NOT NULL,
    created_at        TIMESTAMP NOT NULL,
    resolved_at       TIMESTAMP,
    resolution_status VARCHAR(30) NOT NULL
);
 
CREATE INDEX idx_trades_settle ON trades (settlement_date);
CREATE INDEX idx_trades_cpty   ON trades (counterparty_id);
CREATE INDEX idx_exc_trade     ON exceptions (trade_id);
CREATE INDEX idx_events_trade  ON settlement_events (trade_id, event_timestamp);
