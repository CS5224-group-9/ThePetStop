from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.permissions import AllowAny

from .models import Category, Merchant, Product
from .serializers import (
    CategorySerializer,
    MerchantSerializer,
    ProductDetailSerializer,
    ProductSerializer,
)


class CategoryListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = CategorySerializer
    queryset = Category.objects.all()


class MerchantListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = MerchantSerializer
    queryset = Merchant.objects.filter(active=True).order_by("name")


class MerchantDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = MerchantSerializer
    queryset = Merchant.objects.filter(active=True)
    lookup_field = "slug"


class ProductListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProductSerializer

    def get_queryset(self):
        queryset = Product.objects.filter(active=True, merchant__active=True).select_related(
            "category", "merchant", "group"
        )
        params = self.request.query_params
        query = params.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(name__icontains=query) | Q(description__icontains=query)
                | Q(category__name__icontains=query) | Q(merchant__name__icontains=query)
            )
        for key, field in (("category", "category"), ("merchant", "merchant")):
            value = params.get(key)
            if not value:
                continue
            lookup = f"{field}_id" if value.isdigit() else f"{field}__slug"
            queryset = queryset.filter(**{lookup: value})
        for key, lookup in (("min_price", "gte"), ("max_price", "lte")):
            value = params.get(key)
            if value:
                try:
                    cents = int(value)
                except ValueError:
                    continue
                if cents >= 0:
                    queryset = queryset.filter(**{f"price_cents__{lookup}": cents})
        product_type = params.get("type")
        if product_type in {Product.PRODUCT, Product.SERVICE}:
            queryset = queryset.filter(product_type=product_type)
        species = params.get("species")
        if species:
            queryset = queryset.filter(Q(species__iexact=species) | Q(species__iexact="all pets"))
        sort = params.get("sort")
        if sort == "price_asc":
            queryset = queryset.order_by("price_cents", "name")
        elif sort == "price_desc":
            queryset = queryset.order_by("-price_cents", "name")
        elif sort == "name":
            queryset = queryset.order_by("name")
        return queryset


class ProductDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProductDetailSerializer
    queryset = Product.objects.filter(active=True, merchant__active=True).select_related(
        "category", "merchant", "group"
    )


class MerchantProductListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProductSerializer

    def get_queryset(self):
        merchant = get_object_or_404(Merchant, slug=self.kwargs["slug"], active=True)
        return Product.objects.filter(merchant=merchant, active=True).select_related(
            "category", "merchant", "group"
        )
