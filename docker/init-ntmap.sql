CREATE TABLE ntmap_l1_groups (
    id      SERIAL PRIMARY KEY,
    name    VARCHAR(300) NOT NULL CHECK (name <> '') UNIQUE
);

CREATE TABLE ntmap_l1_maps (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(300) NOT NULL CHECK (name <> '') UNIQUE,
    group_id    INT REFERENCES ntmap_l1_groups(id) NOT NULL,
    scheme      VARCHAR(2000),
    vertical    BOOLEAN NOT NULL
);

GRANT USAGE, SELECT ON SEQUENCE ntmap_l1_maps_id_seq TO ntmap;
GRANT USAGE, SELECT ON SEQUENCE ntmap_l1_groups_id_seq TO ntmap;
GRANT ALL PRIVILEGES ON TABLE ntmap_l1_groups TO ntmap;
GRANT ALL PRIVILEGES ON TABLE ntmap_l1_maps TO ntmap;
ALTER TABLE ntmap_l1_groups OWNER TO ntmap;
ALTER TABLE ntmap_l1_maps OWNER TO ntmap;
