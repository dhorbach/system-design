CREATE TABLE tickets (key text PRIMARY KEY);
CREATE TABLE reservations (
  ticket text PRIMARY KEY REFERENCES tickets(key),
  capacity integer NOT NULL CHECK (capacity <= 16)
);
