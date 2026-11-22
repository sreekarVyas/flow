"""categories + rules, with a Fold-style seed list and seed rules

Revision ID: 0002_categories_rules
Revises: 0001_init
Create Date: 2026-11-22

The seed data is a frozen snapshot. Change it in the app (Categories & rules screen)
or in a new migration, not here.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_categories_rules"
down_revision: str | None = "0001_init"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (parent, icon, [(child, icon), ...])
CATEGORIES: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("Food & drinks", "🍔", [
        ("Eating out", "🍽️"), ("Food delivery", "🛵"), ("Tea & coffee", "☕"),
        ("Snacks & sweets", "🥟"), ("Alcohol", "🍺"),
    ]),
    ("Groceries", "🛒", [
        ("Supermarket", "🏪"), ("Quick commerce", "⚡"), ("Milk & dairy", "🥛"), ("Fruits & vegetables", "🥦"),
    ]),
    ("Transport", "🚕", [
        ("Cab & auto", "🛺"), ("Fuel", "⛽"), ("Bike & car rental", "🏍️"), ("Metro & bus", "🚇"),
        ("Parking & tolls", "🅿️"),
    ]),
    ("Travel", "✈️", [("Flights", "🛫"), ("Trains", "🚆"), ("Bus tickets", "🚌"), ("Hotels", "🏨")]),
    ("Shopping", "🛍️", [
        ("Clothes & shoes", "👕"), ("Electronics", "📱"), ("Home & furniture", "🛋️"),
        ("Online shopping", "📦"), ("Books", "📚"),
    ]),
    ("Bills & utilities", "💡", [
        ("Mobile recharge", "📶"), ("Electricity", "🔌"), ("Internet & DTH", "📡"), ("Gas", "🔥"), ("Water", "🚰"),
    ]),
    ("Subscriptions", "🔁", [
        ("Streaming", "📺"), ("Music", "🎵"), ("Software & AI", "🤖"), ("Cloud storage", "☁️"),
    ]),
    ("Entertainment", "🎬", [("Movies", "🍿"), ("Outings & events", "🎡"), ("Games", "🎮")]),
    ("Home", "🏠", [("Rent", "🔑"), ("Home services", "🧹"), ("Repairs & maintenance", "🔧")]),
    ("Health", "💊", [("Pharmacy", "💊"), ("Doctor", "🩺"), ("Lab tests", "🧪"), ("Fitness", "🏋️")]),
    ("Personal care", "💇", [("Salon & grooming", "💈"), ("Cosmetics", "💄")]),
    ("Jewellery & gold", "💍", []),
    ("Gifts & donations", "🎁", [("Gifts", "🎁"), ("Temple & donations", "🛕"), ("Charity", "🤝")]),
    ("Loans & EMI", "🏦", [("Loan EMI", "📆"), ("Card fees & interest", "💳")]),
    ("Investments", "📈", [("Stocks & mutual funds", "📊"), ("Gold investment", "🪙"), ("Deposits", "🏛️")]),
    ("Education", "🎓", [("Courses", "🧑‍🏫"), ("Exams & fees", "📝")]),
    ("Family", "👨‍👩‍👧", [("Family support", "🫶")]),
    ("Fees & charges", "🧾", [("Bank charges", "🏦"), ("Taxes", "🧾"), ("Fines", "⚠️")]),
    ("Miscellaneous", "❓", [("Cash withdrawal", "💵"), ("Other", "❓")]),
]

# (match_field, match_value, "Parent/Child" or "Parent"). Values are upper case.
# name_contains looks at the payee name only (VPAs carry PSP names like "rxairtel").
# Person names stay out of the repo: the first manual tag learns them.
RULES: list[tuple[str, str, str]] = [
    *[("name_contains", v, "Food & drinks/Eating out") for v in (
        "MC DONALD", "MCDONALD", "GOOD FLIPPIN", "WOW MOMO", "SWIGGY DINERS", "ATLURI FOODS",
        "SRI RAGHAVENDRA", "DOMINO", "KFC", "PIZZA HUT", "BURGER KING", "RESTAURANT")],
    *[("name_contains", v, "Food & drinks/Food delivery") for v in ("SWIGGY", "ZOMATO")],
    *[("name_contains", v, "Food & drinks/Tea & coffee") for v in (
        "RAGHVENDRA TEA", "TEA TYPES", "TEA STALL", "STARBUCKS", "CAFE COFFEE DAY")],
    *[("name_contains", v, "Food & drinks/Snacks & sweets") for v in (
        "TASTE SAMOSA", "KARACHI", "VASIREDDY SWAGRUHA", "CHAT BHANDAR", "BAKERY", "SWEETS")],
    *[("name_contains", v, "Food & drinks/Alcohol") for v in ("WINE MART", "WINE SHOP", "WINES")],
    *[("name_contains", v, "Groceries/Quick commerce") for v in (
        "INSTAMART", "BLINKIT", "BLINK COMMERCE", "ZEPTO", "BIGBASKET")],
    *[("name_contains", v, "Groceries/Supermarket") for v in (
        "VIJETHA", "RELIANCE RETAIL", "DMART", "AVENUE SUPERMARTS", "RATNADEEP", "SUPERMARKET", "SUPER MARKET")],
    *[("name_contains", v, "Groceries/Milk & dairy") for v in ("ORGANIC MILK", "MILK")],
    *[("name_contains", v, "Transport/Fuel") for v in ("BPCL", "HPCL", "IOCL", "FILLING", "PETRO", "FUEL")],
    *[("name_contains", v, "Transport/Cab & auto") for v in ("UBER INDIA", "RAPIDO", "OLA CABS", "ANI TECHNOLOGIES")],
    *[("name_contains", v, "Transport/Bike & car rental") for v in ("ROYALBROTHERS", "ROYAL BROTHERS")],
    ("name_contains", "METRO RAIL", "Transport/Metro & bus"),
    ("name_contains", "FASTAG", "Transport/Parking & tolls"),
    ("name_contains", "IRCTC", "Travel/Trains"),
    *[("name_contains", v, "Shopping/Clothes & shoes") for v in ("MYNTRA", "AJIO")],
    *[("name_contains", v, "Shopping/Online shopping") for v in ("AMAZON", "FLIPKART")],
    ("name_contains", "CROMA", "Shopping/Electronics"),
    *[("name_contains", v, "Subscriptions") for v in ("APPLE MEDIA", "APPLE SERVICES", "GOOGLE PLAY")],
    *[("name_contains", v, "Subscriptions/Streaming") for v in (
        "JIOHOTSTAR", "JIOSTAR", "HOTSTAR", "NETFLIX", "PRIME VIDEO")],
    ("name_contains", "SPOTIFY", "Subscriptions/Music"),
    *[("name_contains", v, "Subscriptions/Software & AI") for v in ("OPENAI", "ANTHROPIC")],
    ("vpa_contains", "LITY@AXISB", "Bills & utilities"),  # CRED utility payments
    *[("name_contains", v, "Bills & utilities/Mobile recharge") for v in ("AIRTEL", "RELIANCE JIO")],
    *[("name_contains", v, "Bills & utilities/Electricity") for v in ("TSSPDCL", "ELECTRICITY")],
    *[("name_contains", v, "Entertainment/Movies") for v in ("BOOKMYSHOW", "BOOK MY SHOW", "PVR", "INOX")],
    ("name_contains", "SHILPARAMAM", "Entertainment/Outings & events"),
    *[("name_contains", v, "Home/Home services") for v in ("URBANCLAP", "URBAN COMPANY")],
    *[("name_contains", v, "Health/Pharmacy") for v in ("PHARMA", "APOLLO", "MEDICAL")],
    *[("name_contains", v, "Jewellery & gold") for v in ("NATHU AND SONS", "JEWELLER", "ALPHA GOLD")],
    ("name_contains", "TEMPLE", "Gifts & donations/Temple & donations"),
    ("name_contains", "LOAN EMI", "Loans & EMI/Loan EMI"),
    *[("name_contains", v, "Investments/Stocks & mutual funds") for v in ("GROWW", "INDIAN CLEARING", "ZERODHA")],
]


def upgrade() -> None:
    categories = op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=True),
        sa.Column("icon", sa.String(16), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("archived", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_seed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.UniqueConstraint(
            "parent_id", "name", name="uq_categories_parent_name", postgresql_nulls_not_distinct=True
        ),
    )
    op.create_index("ix_categories_parent_id", "categories", ["parent_id"])

    rules = op.create_table(
        "rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("match_field", sa.String(16), nullable=False),
        sa.Column("match_value", sa.String(255), nullable=False),
        sa.Column("direction", sa.String(6), nullable=True),
        sa.Column(
            "category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("kind", sa.String(16), nullable=True),
        sa.Column("priority", sa.Integer(), server_default="0", nullable=False),
        sa.Column("source", sa.String(8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "match_field", "match_value", "direction", name="uq_rules_match", postgresql_nulls_not_distinct=True
        ),
        sa.CheckConstraint(
            "match_field IN ('payee', 'name_contains', 'vpa_contains')", name="ck_rules_match_field"
        ),
        sa.CheckConstraint("source IN ('seed', 'learned')", name="ck_rules_source"),
        sa.CheckConstraint("direction IS NULL OR direction IN ('debit', 'credit')", name="ck_rules_direction"),
        sa.CheckConstraint(
            "kind IS NULL OR kind IN ('expense', 'transfer', 'settlement', 'income', 'refund')",
            name="ck_rules_kind",
        ),
        sa.CheckConstraint("category_id IS NOT NULL OR kind IS NOT NULL", name="ck_rules_has_action"),
    )
    op.create_index("ix_rules_category_id", "rules", ["category_id"])

    op.create_foreign_key(
        "fk_transactions_category_id", "transactions", "categories", ["category_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_transactions_category_id", "transactions", ["category_id"])

    # ---- seed ----
    conn = op.get_bind()
    ids: dict[str, int] = {}
    for p_order, (parent, icon, children) in enumerate(CATEGORIES):
        pid = conn.execute(
            categories.insert()
            .values(name=parent, icon=icon, sort_order=p_order, is_seed=True)
            .returning(categories.c.id)
        ).scalar_one()
        ids[parent] = pid
        for c_order, (child, c_icon) in enumerate(children):
            ids[f"{parent}/{child}"] = conn.execute(
                categories.insert()
                .values(name=child, parent_id=pid, icon=c_icon, sort_order=c_order, is_seed=True)
                .returning(categories.c.id)
            ).scalar_one()
    op.bulk_insert(
        rules,
        [
            {"match_field": f, "match_value": v, "category_id": ids[path], "source": "seed", "priority": 0}
            for f, v, path in RULES
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_category_id", table_name="transactions")
    op.drop_constraint("fk_transactions_category_id", "transactions", type_="foreignkey")
    op.execute("UPDATE transactions SET category_id = NULL, category_source = NULL")
    op.drop_index("ix_rules_category_id", table_name="rules")
    op.drop_table("rules")
    op.drop_index("ix_categories_parent_id", table_name="categories")
    op.drop_table("categories")
