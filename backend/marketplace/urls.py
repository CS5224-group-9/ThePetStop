from django.urls import path

from . import views

urlpatterns = [
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
]
