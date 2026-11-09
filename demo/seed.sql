CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    store_id TEXT NOT NULL,
    item TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('general', 'electronics')),
    purchased_on TEXT NOT NULL,
    channel TEXT NOT NULL,
    status TEXT NOT NULL,
    final_sale INTEGER NOT NULL DEFAULT 0 CHECK (final_sale IN (0, 1))
);

INSERT OR IGNORE INTO orders VALUES
    ('NM-1042', 'STORE-014', 'Trailway daypack', 'general', '2026-10-30', 'Online', 'Delivered', 0),
    ('NM-1043', 'STORE-014', 'Aero wireless headphones', 'electronics', '2026-11-02', 'In-store', 'Collected', 0),
    ('NM-1044', 'STORE-014', 'Harbor desk lamp', 'general', '2026-09-25', 'In-store', 'Collected', 0),
    ('NM-1045', 'STORE-014', 'Northline travel mug', 'general', '2026-11-08', 'Online', 'Ready for pickup', 0),
    ('NM-1046', 'STORE-014', 'Seasonal glassware set', 'general', '2026-11-06', 'In-store', 'Collected', 1),
    ('NM-2042', 'STORE-027', 'Cedar table lamp', 'general', '2026-11-03', 'Online', 'Delivered', 0);
