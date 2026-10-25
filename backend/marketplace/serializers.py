from rest_framework import serializers

from .models import Category, Merchant, Product


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
            "id", "name", "slug", "description", "species", "size", "price_cents",
            "stock", "product_type", "duration_minutes", "category", "merchant",
            "image_key", "image_url",
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
            Product.objects.filter(group_id=obj.group_id, active=True, merchant__active=True)
            .exclude(pk=obj.pk)
            .select_related("merchant", "category")
            .order_by("price_cents", "merchant__name")
        )
        return ProductOfferSerializer(peers, many=True, context=self.context).data


class ProductOfferSerializer(serializers.ModelSerializer):
    merchant = MerchantSerializer(read_only=True)

    class Meta:
        model = Product
        fields = ["id", "name", "price_cents", "stock", "merchant"]
