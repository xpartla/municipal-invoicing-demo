"""ORM models, repositories and adapters of the intake context: they implement the domain's
repository protocols and the application's ports. ORM objects never leave this package; every
repository method for customer data takes `customer_id`."""
