from django.conf import settings
from django.db import models


class Merchant(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    logo_key = models.CharField(max_length=512, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="merchants",
    )
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class ProductGroup(models.Model):
    canonical_name = models.CharField(max_length=200, unique=True)

    def __str__(self):
        return self.canonical_name


class Product(models.Model):
    PRODUCT = "product"
    SERVICE = "service"
    TYPE_CHOICES = [(PRODUCT, "Product"), (SERVICE, "Service")]

    merchant = models.ForeignKey(
        Merchant, on_delete=models.PROTECT, related_name="products"
    )
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="products"
    )
    group = models.ForeignKey(
        ProductGroup,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="products",
    )
    name = models.CharField(max_length=200)
    slug = models.SlugField()
    description = models.TextField(blank=True)
    species = models.CharField(max_length=40, default="all pets")
    size = models.CharField(max_length=100, blank=True)
    price_cents = models.PositiveIntegerField()
    stock = models.PositiveIntegerField(default=0)
    image_key = models.CharField(max_length=512, blank=True)
    product_type = models.CharField(
        max_length=12, choices=TYPE_CHOICES, default=PRODUCT
    )
    duration_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["merchant", "slug"],
                name="marketplace_product_merchant_slug_uniq",
            )
        ]
        ordering = ["name", "merchant__name"]
        indexes = [
            models.Index(
                fields=["active", "category"],
                name="mkt_active_category_idx",
            ),
            models.Index(
                fields=["active", "price_cents"],
                name="marketplace_active_price_idx",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.merchant})"


class CartItem(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart_items"
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="cart_items"
    )
    quantity = models.PositiveSmallIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "product"], name="marketplace_cart_user_product_uniq"
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1),
                name="marketplace_cart_quantity_gte_1",
            ),
        ]

    def __str__(self):
        return f"Cart item {self.product_id} for user {self.user_id}"


class Order(models.Model):
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"
    CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (PENDING_PAYMENT, "Pending payment"),
        (PAID, "Paid"),
        (CANCELLED, "Cancelled"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="marketplace_orders",
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=PENDING_PAYMENT
    )
    total_cents = models.PositiveIntegerField(default=0)
    shipping_name = models.CharField(max_length=160)
    shipping_phone = models.CharField(max_length=40)
    shipping_address = models.TextField()
    shipping_postal_code = models.CharField(max_length=12)
    payment_ref = models.CharField(max_length=80, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order {self.pk} ({self.status})"


class MerchantOrder(models.Model):
    PAID = "paid"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (value, value.replace("_", " ").title())
        for value in (PAID, PROCESSING, SHIPPED, DELIVERED, CANCELLED)
    ]

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="merchant_orders"
    )
    merchant = models.ForeignKey(
        Merchant, on_delete=models.PROTECT, related_name="orders"
    )
    subtotal_cents = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PAID)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["order", "merchant"],
                name="marketplace_order_merchant_uniq",
            )
        ]

    def __str__(self):
        return f"Merchant order {self.pk} ({self.status})"


class OrderItem(models.Model):
    merchant_order = models.ForeignKey(
        MerchantOrder, on_delete=models.CASCADE, related_name="items"
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="order_items"
    )
    product_name = models.CharField(max_length=200)
    unit_price_cents = models.PositiveIntegerField()
    quantity = models.PositiveSmallIntegerField()

    def __str__(self):
        return f"{self.product_name} x {self.quantity}"
