/**
 * Centralized ECharts color palettes for dark/light themes.
 * Import getChartColors() in any ECharts component and call with ThemeService.isDark().
 */

export interface ChartColors {
  tooltipBg: string;
  tooltipBorder: string;
  tooltipText: string;
  axisLine: string;
  axisLabel: string;
  splitLine: string;
  textPrimary: string;
  textSecondary: string;
  textMuted: string;
  surface: string;
  bg: string;
  border: string;
}

const DARK: ChartColors = {
  tooltipBg: '#1a1d2e',
  tooltipBorder: '#2d3154',
  tooltipText: '#e2e8f0',
  axisLine: '#2d3154',
  axisLabel: '#8892a4',
  splitLine: '#252845',
  textPrimary: '#e2e8f0',
  textSecondary: '#a0aec0',
  textMuted: '#8892a4',
  surface: '#1a1d2e',
  bg: '#0f1117',
  border: '#2d3154',
};

const LIGHT: ChartColors = {
  tooltipBg: '#ffffff',
  tooltipBorder: '#d1d5db',
  tooltipText: '#1f2937',
  axisLine: '#d1d5db',
  axisLabel: '#6b7280',
  splitLine: '#e5e7eb',
  textPrimary: '#1f2937',
  textSecondary: '#4b5563',
  textMuted: '#9ca3af',
  surface: '#ffffff',
  bg: '#f3f4f6',
  border: '#d1d5db',
};

export function getChartColors(isDark: boolean): ChartColors {
  return isDark ? DARK : LIGHT;
}
