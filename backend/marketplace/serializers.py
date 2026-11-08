from django.core.validators import RegexValidator
from rest_framework import serializers

from .models import Category, Merchant, MerchantOrder, Order, OrderItem, Product

MAX_CART_QUANTITY = 99


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug", "sort_order"]


class MerchantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Merchant
        fields = ["id", "name", "slug", "description", "logo_key"]


class ProductSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    merchant = MerchantSerializer(read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "species",
            "size",
            "price_cents",
            "stock",
            "product_type",
            "duration_minutes",
            "category",
            "merchant",
            "image_key",
            "image_url",
        ]

    def get_image_url(self, obj):
        if not obj.image_key:
            return None
        if obj.image_key.startswith(("https://", "http://")):
            return obj.image_key
        # Product image delivery is added by D3 with the product-images bucket.
        return None


class ProductDetailSerializer(ProductSerializer):
    also_sold_by = serializers.SerializerMethodField()

    class Meta(ProductSerializer.Meta):
        fields = [*ProductSerializer.Meta.fields, "also_sold_by"]

    def get_also_sold_by(self, obj):
        if not obj.group_id:
            return []
        peers = (
            Product.objects.filter(
                group_id=obj.group_id, active=True, merchant__active=True
            )
            .exclude(pk=obj.pk)
            .select_related("merchant", "category")
            .order_by("price_cents", "merchant__name")
        )
        return ProductOfferSerializer(peers, many=True, context=self.context).data


class ProductOfferSerializer(serializers.ModelSerializer):
    merchant = MerchantSerializer(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "size",
            "species",
            "price_cents",
            "stock",
            "merchant",
        ]


class MerchantRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Merchant
        fields = ["id", "name", "slug"]


# Cart


def cart_payload(user, context) -> dict:
    """GET cart/: lines grouped by merchant, with the current catalogue prices."""
    lines = (
        user.cart_items.select_related("product__category", "product__merchant")
        .order_by("product__merchant__name", "product__merchant_id", "product__name")
        .all()
    )
    groups: dict[int, dict] = {}
    total = 0
    for line in lines:
        product = line.product
        group = groups.setdefault(
            product.merchant_id,
            {
                "merchant": MerchantRefSerializer(product.merchant).data,
                "items": [],
            },
        )
        group["items"].append(
            {
                "product": ProductSerializer(product, context=context).data,
                "quantity": line.quantity,
            }
        )
        total += product.price_cents * line.quantity
    return {"merchants": list(groups.values()), "total_cents": total}


class CartAddSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(active=True, merchant__active=True)
    )
    quantity = serializers.IntegerField(
        min_value=1, max_value=MAX_CART_QUANTITY, default=1
    )


class CartQuantitySerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1, max_value=MAX_CART_QUANTITY)


# Checkout


class ShippingSerializer(serializers.Serializer):
    shipping_name = serializers.CharField(max_length=160)
    shipping_phone = serializers.CharField(
        max_length=40,
        validators=[
            RegexValidator(
                r"^\+?[0-9]{8,15}$", "Enter a phone number of 8 to 15 digits."
            )
        ],
    )
    shipping_address = serializers.CharField(max_length=500)
    shipping_postal_code = serializers.CharField(
        max_length=12,
        validators=[RegexValidator(r"^[0-9]{6}$", "Enter a 6-digit postal code.")],
    )


# Orders


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ["product", "product_name", "unit_price_cents", "quantity"]


class MerchantOrderSerializer(serializers.ModelSerializer):
    merchant = MerchantRefSerializer(read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = MerchantOrder
        fields = ["id", "merchant", "status", "subtotal_cents", "items"]


class OrderSerializer(serializers.ModelSerializer):
    merchant_orders = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "status",
            "created_at",
            "total_cents",
            "shipping_name",
            "shipping_phone",
            "shipping_address",
            "shipping_postal_code",
            "payment_ref",
            "paid_at",
            "merchant_orders",
        ]

    def get_merchant_orders(self, obj):
        # Uses the prefetch from the view; ordered by shop name like the cart
        rows = sorted(obj.merchant_orders.all(), key=lambda m: (m.merchant.name, m.pk))
        return MerchantOrderSerializer(rows, many=True).data
