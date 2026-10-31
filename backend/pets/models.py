from django.conf import settings
from django.db import models
class pet(models.Model):
    class SPECIES(models.TextChoices):
        DOG = "dog", "Dog"
        CAT = "cat", "Cat"
        FISH = "fish", "Fish"
        BIRD = "bird", "Bird"
        RABBIT = "rabbit", "Rabbit"
        HAMESTER = "hamster", "Hamster"
        OTHER = "other", "Other"
    class SEX(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        UNKNOWN = "unknown", "Unknown"
    name =models.CharField(max_length=200)
    species = models.CharField(
            max_length=100,
            choices=SPECIES.choices,
            default=SPECIES.DOG,
        )
    breeds = models.CharField(max_length=100, blank=True)
    sex = models.CharField(
            max_length=10,
            choices=SEX.choices,
            default=SEX.UNKNOWN,
        )
    date_of_birth = models.DateField(null=True, blank=True)
    microchip_no = models.CharField(max_length=1000, null=True,blank= True)
    photo_key= models.CharField(max_length=1000, blank=True)
    allergies =models.JSONField(default=list, blank=True)
    diet_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pets"
    )
    class Meta:
        ordering=["name","id"]
    
    def __str__(self):
        return self.name

    