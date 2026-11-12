from django.urls import path

from . import views

urlpatterns = [
    path(
        "merchant/orders/",
        views.OwnedMerchantOrderListView.as_view(),
        name="owned-merchant-order-list",
    ),
    path(
        "merchant/orders/<int:pk>/",
        views.OwnedMerchantOrderDetailView.as_view(),
        name="owned-merchant-order-detail",
    ),
    path(
        "merchant/products/",
        views.OwnedMerchantProductListCreateView.as_view(),
        name="owned-merchant-product-list",
    ),
    path(
        "merchant/products/<int:pk>/",
        views.OwnedMerchantProductDetailView.as_view(),
        name="owned-merchant-product-detail",
    ),
    path(
        "merchant/products/<int:pk>/image-upload/",
        views.OwnedMerchantProductImageUploadView.as_view(),
        name="owned-merchant-product-image-upload",
    ),
    path(
        "merchant/products/<int:pk>/image-upload/complete/",
        views.OwnedMerchantProductImageCompleteView.as_view(),
        name="owned-merchant-product-image-upload-complete",
    ),
    path("categories/", views.CategoryListView.as_view(), name="category-list"),
    path("merchants/", views.MerchantListView.as_view(), name="merchant-list"),
    path(
        "merchants/<slug:slug>/",
        views.MerchantDetailView.as_view(),
        name="merchant-detail",
    ),
    path(
        "merchants/<slug:slug>/products/",
        views.MerchantProductListView.as_view(),
        name="merchant-products",
    ),
    path("products/", views.ProductListView.as_view(), name="product-list"),
    path(
        "products/<int:pk>/", views.ProductDetailView.as_view(), name="product-detail"
    ),
    path("cart/", views.CartView.as_view(), name="cart"),
    path("cart/items/", views.CartItemListView.as_view(), name="cart-items"),
    path(
        "cart/items/<int:product_id>/",
        views.CartItemDetailView.as_view(),
        name="cart-item-detail",
    ),
    path("checkout/", views.CheckoutView.as_view(), name="checkout"),
    path("orders/", views.OrderListView.as_view(), name="order-list"),
    path("orders/<int:pk>/", views.OrderDetailView.as_view(), name="order-detail"),
]
