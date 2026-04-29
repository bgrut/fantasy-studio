// Human-readable labels for V1.3 template_v2 recipes. Frontend-only dictionary;
// add entries as the backend adds new named recipes. Returns null when the
// badge should be hidden (unknown recipe OR the _default fall-through).

const RECIPE_DISPLAY_NAMES: Record<string, string> = {
  hero_mountain_establishing: 'Mountain establishing shot',
  cat_canyon_cinematic: 'Canyon cinematic',
  hero_desert_epic: 'Epic desert wide',
  hero_city_street_night: 'Night street scene',
  hero_city_day: 'Daylight street scene',
  hero_forest_intimate: 'Forest intimate',
  hero_castle_dramatic: 'Castle dramatic',
  hero_ocean_horizon: 'Ocean horizon',
  vehicle_desert_hero: 'Desert vehicle hero',
  vehicle_street_chase: 'Street chase',
  vehicle_mountain_road: 'Mountain road',
  animal_mountain_walk: 'Mountain walk',
  animal_forest_intimate: 'Forest intimate (animal)',
  robot_city_night: 'Neon cyberpunk',
  multi_character_stage: 'Studio character stage',
}

export function recipeDisplayName(raw: string | null | undefined): string | null {
  if (!raw) return null
  const key = String(raw).trim().toLowerCase()
  if (!key || key === '_default') return null
  return RECIPE_DISPLAY_NAMES[key] || null
}
