import { useQuery } from "@tanstack/react-query";
import { api, type DayRow, type HourRow, type LevelRow } from "../lib/api";

// The dataset is a fixed historical snapshot, so responses never go stale.
const STATIC = { staleTime: Infinity, retry: 1 } as const;

export const useHealth = () => useQuery({ queryKey: ["health"], queryFn: api.health, ...STATIC });

export const useForecast = (deliveryDate: string | undefined, cutoff: string) =>
  useQuery({
    queryKey: ["forecast", deliveryDate, cutoff],
    queryFn: () => api.forecast(deliveryDate as string, cutoff),
    enabled: !!deliveryDate,
    ...STATIC,
  });

export const useAccuracy = (cutoff: string) =>
  useQuery({ queryKey: ["accuracy", cutoff], queryFn: () => api.accuracy(cutoff), ...STATIC });

export const useHourBreakdown = (cutoff: string) =>
  useQuery({
    queryKey: ["breakdown", "hour", cutoff],
    queryFn: () => api.breakdown<HourRow>("hour", cutoff),
    ...STATIC,
  });

export const useLevelBreakdown = (cutoff: string, basis: "actual" | "forecast") =>
  useQuery({
    queryKey: ["breakdown", "level", cutoff, basis],
    queryFn: () => api.breakdown<LevelRow>("level", cutoff, basis),
    ...STATIC,
  });

export const useDayBreakdown = (cutoff: string) =>
  useQuery({
    queryKey: ["breakdown", "day", cutoff],
    queryFn: () => api.breakdown<DayRow>("day", cutoff),
    ...STATIC,
  });

export const useSensitivity = () =>
  useQuery({ queryKey: ["sensitivity"], queryFn: api.sensitivity, ...STATIC });
