import { blink } from '@/blink/client';

export interface SystemSetting {
  id: string;
  key: string;
  value: string;
  description: string;
  updatedAt: string;
}

export const SYSTEM_SETTING_KEYS = {
  BLENDER_ENABLED: 'BLENDER_ENABLED',
  BLENDER_EXECUTABLE_PATH: 'BLENDER_EXECUTABLE_PATH',
  BLENDER_TEMPLATE_ROOT: 'BLENDER_TEMPLATE_ROOT',
  BLENDER_OUTPUT_ROOT: 'BLENDER_OUTPUT_ROOT',
  LOCAL_RENDER_MODE: 'LOCAL_RENDER_MODE',
} as const;

export async function getSystemSettings(): Promise<SystemSetting[]> {
  const data = await blink.db.sql('SELECT * FROM system_settings');
  return data.rows as any[];
}

export async function getSystemSetting(key: string): Promise<string | null> {
  const data = await blink.db.sql('SELECT value FROM system_settings WHERE key = ?', [key]);
  if (data.rows.length > 0) {
    return (data.rows[0] as any).value;
  }
  return null;
}

export async function updateSystemSetting(key: string, value: string): Promise<void> {
  await blink.db.sql(
    'UPDATE system_settings SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?',
    [value, key]
  );
}

export async function isLocalRenderMode(): Promise<boolean> {
  const value = await getSystemSetting(SYSTEM_SETTING_KEYS.LOCAL_RENDER_MODE);
  return value === 'true';
}

export async function isBlenderEnabled(): Promise<boolean> {
  const value = await getSystemSetting(SYSTEM_SETTING_KEYS.BLENDER_ENABLED);
  return value === 'true';
}
