from django.contrib import admin

from .models import (
    CartItem,
    Category,
    Merchant,
    MerchantOrder,
    Order,
    OrderItem,
    Product,
    ProductGroup,
)


@admin.register(Merchant)
class MerchantAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "active")
    search_fields = ("name", "slug")
    list_filter = ("active",)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "sort_order")
    ordering = ("sort_order", "name")


@admin.register(ProductGroup)
class ProductGroupAdmin(admin.ModelAdmin):
    search_fields = ("canonical_name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "merchant", "category", "price_cents", "stock", "active")
    list_filter = ("active", "category", "merchant")
    search_fields = ("name", "slug", "description")


admin.site.register([CartItem, Order, MerchantOrder, OrderItem])
