from scripts.bootstrap_airtable import TABLE_SCHEMAS, build_plan


def test_schema_plan_creates_missing_tables_once():
    plan = build_plan([], {"Customers": TABLE_SCHEMAS["Customers"]})
    assert len(plan) == 1
    assert plan[0].action == "create_table"
    assert plan[0].table_name == "Customers"


def test_schema_plan_adds_only_missing_fields():
    existing = [
        {
            "id": "tblCustomers",
            "name": "Customers",
            "fields": [{"name": "Customer ID"}, {"name": "Name"}],
        }
    ]
    plan = build_plan(existing, {"Customers": TABLE_SCHEMAS["Customers"]})
    assert [operation.field["name"] for operation in plan] == [
        "Phone",
        "Email",
        "Created At",
        "Vehicle",
        "Registration",
        "Preferred Branch",
        "Last Interaction",
        "Current Status",
    ]
    assert all(operation.action == "create_field" for operation in plan)
    assert all(operation.table_id == "tblCustomers" for operation in plan)


def test_schema_plan_is_empty_for_compatible_schema():
    existing = [
        {
            "id": "tblCustomers",
            "name": "Customers",
            "fields": [{"name": field["name"]} for field in TABLE_SCHEMAS["Customers"]],
        }
    ]
    assert build_plan(existing, {"Customers": TABLE_SCHEMAS["Customers"]}) == []
