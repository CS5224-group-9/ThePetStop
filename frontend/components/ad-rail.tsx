import { Badge, Icon } from "./ui";

// shortcut: static fictional ads, replace this list with managed placements when campaigns are introduced.
const ads = [
  {
    brand: "Paw Pantry",
    title: "Good food. Happy tails.",
    description: "Make room for everyday favourites in your pet's pantry.",
    icon: "bag",
    tone: "teal",
    action: "Open ad preview",
    href: "about:blank",
  },
  {
    brand: "Whisker & Co.",
    title: "A little play, every day.",
    description: "Find something new for curious paws and playful companions.",
    icon: "paw",
    tone: "amber",
    action: "Open ad preview",
    href: "about:blank",
  },
  {
    brand: "Good Pet Supply",
    title: "Everyday care, made simple.",
    description: "Compare essentials from our fictional neighbourhood shops.",
    icon: "box",
    tone: "neutral",
    action: "Open ad preview",
    href: "about:blank",
  },
];

export function AdRail() {
  return (
    <aside className="site-ad-rail" aria-label="Advertisements">
      <div className="site-ad-slots">
        {ads.map((ad) => (
          <article className={`site-ad ${ad.tone}`} key={ad.brand}>
            <Badge tone="amber">Advertisement · Demo</Badge>
            <Icon name={ad.icon} size={32} />
            <p className="site-ad-brand">{ad.brand}</p>
            <h3>{ad.title}</h3>
            <p>{ad.description}</p>
            <a
              href={ad.href}
              className="text-link"
              target="_blank"
              rel="noopener noreferrer"
              title="Opens in a new tab"
              aria-label={`${ad.brand}: ${ad.action} (opens in a new tab)`}
            >
              {ad.action} <Icon name="arrow" size={16} />
            </a>
          </article>
        ))}
      </div>
    </aside>
  );
}
