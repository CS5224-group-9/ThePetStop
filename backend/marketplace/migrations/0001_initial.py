from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="Category",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("slug", models.SlugField(unique=True)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
            ],
            options={"ordering": ["sort_order", "name"]},
        ),
        migrations.CreateModel(
            name="Merchant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("slug", models.SlugField(unique=True)),
                ("description", models.TextField(blank=True)),
                ("logo_key", models.CharField(blank=True, max_length=512)),
                ("active", models.BooleanField(default=True)),
                ("owner", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="merchants", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="ProductGroup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("canonical_name", models.CharField(max_length=200, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name="Order",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("pending_payment", "Pending payment"), ("paid", "Paid"), ("cancelled", "Cancelled")], default="pending_payment", max_length=20)),
                ("total_cents", models.PositiveIntegerField(default=0)),
                ("shipping_name", models.CharField(max_length=160)),
                ("shipping_phone", models.CharField(max_length=40)),
                ("shipping_address", models.TextField()),
                ("shipping_postal_code", models.CharField(max_length=12)),
                ("payment_ref", models.CharField(blank=True, max_length=80)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="marketplace_orders", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="Product",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("slug", models.SlugField()),
                ("description", models.TextField(blank=True)),
                ("species", models.CharField(default="all pets", max_length=40)),
                ("size", models.CharField(blank=True, max_length=100)),
                ("price_cents", models.PositiveIntegerField()),
                ("stock", models.PositiveIntegerField(default=0)),
                ("image_key", models.CharField(blank=True, max_length=512)),
                ("product_type", models.CharField(choices=[("product", "Product"), ("service", "Service")], default="product", max_length=12)),
                ("duration_minutes", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("category", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="products", to="marketplace.category")),
                ("group", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="products", to="marketplace.productgroup")),
                ("merchant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="products", to="marketplace.merchant")),
            ],
            options={"ordering": ["name", "merchant__name"]},
        ),
        migrations.CreateModel(
            name="CartItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.PositiveSmallIntegerField(default=1)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cart_items", to="marketplace.product")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cart_items", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="MerchantOrder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("subtotal_cents", models.PositiveIntegerField()),
                ("status", models.CharField(choices=[("paid", "Paid"), ("processing", "Processing"), ("shipped", "Shipped"), ("delivered", "Delivered"), ("cancelled", "Cancelled")], default="paid", max_length=20)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("merchant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="orders", to="marketplace.merchant")),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="merchant_orders", to="marketplace.order")),
            ],
        ),
        migrations.CreateModel(
            name="OrderItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("product_name", models.CharField(max_length=200)),
                ("unit_price_cents", models.PositiveIntegerField()),
                ("quantity", models.PositiveSmallIntegerField()),
                ("merchant_order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="marketplace.merchantorder")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="order_items", to="marketplace.product")),
            ],
        ),
        migrations.AddConstraint(model_name="product", constraint=models.UniqueConstraint(fields=("merchant", "slug"), name="marketplace_product_merchant_slug_uniq")),
        migrations.AddIndex(model_name="product", index=models.Index(fields=["active", "category"], name="marketplace_active_category_idx")),
        migrations.AddIndex(model_name="product", index=models.Index(fields=["active", "price_cents"], name="marketplace_active_price_idx")),
        migrations.AddConstraint(model_name="cartitem", constraint=models.UniqueConstraint(fields=("user", "product"), name="marketplace_cart_user_product_uniq")),
        migrations.AddConstraint(model_name="cartitem", constraint=models.CheckConstraint(condition=models.Q(("quantity__gte", 1)), name="marketplace_cart_quantity_gte_1")),
        migrations.AddConstraint(model_name="merchantorder", constraint=models.UniqueConstraint(fields=("order", "merchant"), name="marketplace_order_merchant_uniq")),
    ]
