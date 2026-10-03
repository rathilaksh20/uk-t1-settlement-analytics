CREATE TABLE counterparty_profile (
    counterparty_id VARCHAR(20) PRIMARY KEY REFERENCES counterparties(counterparty_id),
    reliability     NUMERIC(5,3) NOT NULL,
    responsiveness  NUMERIC(5,3) NOT NULL
);

CREATE TABLE stage_durations (
    trade_id           VARCHAR(30) PRIMARY KEY REFERENCES trades(trade_id),
    confirmation_hours NUMERIC(10,3) NOT NULL,
    matching_hours     NUMERIC(10,3) NOT NULL,
    instruction_hours  NUMERIC(10,3) NOT NULL,
    shock_day          BOOLEAN NOT NULL
);

CREATE TABLE settlement_flags (
    trade_id  VARCHAR(30) NOT NULL REFERENCES trades(trade_id),
    flag_type VARCHAR(40) NOT NULL,
    PRIMARY KEY (trade_id, flag_type)
);

CREATE INDEX idx_flags_type ON settlement_flags (flag_type);