# ABOUTME: Constants for the device_role integration.
# ABOUTME: Domain name, platform list, storage keys, and default thresholds.

DOMAIN = "device_role"

PLATFORMS = ["sensor", "binary_sensor", "switch"]

# Storage
STORAGE_KEY = f"{DOMAIN}_accumulators"
STORAGE_VERSION = 1
STORAGE_SAVE_INTERVAL = 1800  # 30 minutes in seconds

# Config entry data keys
CONF_ROLE_NAME = "role_name"
CONF_DEVICE_ID = "device_id"
CONF_ACTIVE = "active"
CONF_ENTITY_MAPPINGS = "entity_mappings"

# Entity mapping keys
CONF_SLOT = "slot"
CONF_SOURCE_UNIQUE_ID = "source_unique_id"
CONF_SOURCE_ENTITY_ID = "source_entity_id"
CONF_DOMAIN = "domain"
CONF_DEVICE_CLASS = "device_class"
CONF_STATE_CLASS = "state_class"

# Accumulator defaults
RESET_DROP_FRACTION = 0.1  # Drops > 10% of last reading treated as device reset
