export const approvedAnimalLabels = {
  dog: "Dogs",
  cat: "Cats",
  small_mammal: "Small mammals",
  bird: "Birds",
  marine_fish: "Marine fish",
  freshwater_fish: "Freshwater fish",
};
export type ApprovedAnimal = keyof typeof approvedAnimalLabels;
