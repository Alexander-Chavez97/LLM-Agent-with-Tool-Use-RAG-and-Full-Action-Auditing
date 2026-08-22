-- Small seed table for the db_query tool to query. Deliberately separate
-- from the agent's own operational tables (sessions/messages/action_log)
-- -- this is "business data" the agent answers questions about, not data
-- the agent manages itself.

CREATE TABLE products (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    category    TEXT NOT NULL,
    price_usd   NUMERIC(10, 2) NOT NULL,
    in_stock    BOOLEAN NOT NULL DEFAULT true
);

INSERT INTO products (name, category, price_usd, in_stock) VALUES
    ('Mechanical Keyboard', 'Electronics', 89.99, true),
    ('USB-C Hub', 'Electronics', 24.50, true),
    ('Standing Desk', 'Furniture', 349.00, false),
    ('Ergonomic Chair', 'Furniture', 210.00, true),
    ('Wireless Mouse', 'Electronics', 19.99, true),
    ('Monitor Arm', 'Furniture', 45.00, true),
    ('Noise Cancelling Headphones', 'Electronics', 149.99, false),
    ('Webcam 1080p', 'Electronics', 39.99, true),
    ('Desk Lamp', 'Furniture', 22.00, true),
    ('Laptop Stand', 'Furniture', 29.99, true);
