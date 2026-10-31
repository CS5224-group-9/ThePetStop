from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from .models import pet
from .serializers import PetSerializers

class PetListCreateView(generics.ListAPIView):
    serializer_class = PetSerializers
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        return pet.objects.filter(owner=self.request.user)
    
    def perform_create(self,serializer):
        serializer.save(owner=self.request.user)
        
class PetDetailView(generics.RetrieveDestroyAPIView):
    serializer_class=PetSerializers
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        return pet.objects.filter(owner=self.request.user)