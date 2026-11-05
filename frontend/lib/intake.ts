import { ContractError, text } from "./api-contracts";
export const priorities = ["Room choices without a room-rent limit", "A shorter wait for pre-existing conditions", "No co-payment, where available", "Cashless hospitals near me", "Day-care treatment cover", "Restoration or recharge benefit", "Maternity and newborn cover", "Cover for non-medical items"];
export const budgets = ["Under ₹15,000 a year", "₹15,000–₹25,000 a year", "₹25,000–₹40,000 a year", "₹40,000–₹60,000 a year", "Above ₹60,000 a year", "I am still exploring the cost"];
export const covers = ["Active retail health policy", "Employer cover", "No existing cover", "Unsure about existing cover"];
export interface Intake { adults: string; children: string; age: string; city: string; priorities: string[]; budget: string; cover: string }
export function intakeQuestion(value: Intake): string {
  if (!["1", "2", "3"].includes(value.adults) || !["0", "1", "2", "3"].includes(value.children) || !/^\d{2}$/.test(value.age) || Number(value.age) < 18 || Number(value.age) > 99 || !["tier_1", "tier_2", "tier_3"].includes(value.city)) throw new ContractError("Check the household details, age and treatment city.");
  if (!budgets.includes(value.budget) || !covers.includes(value.cover) || value.priorities.length > priorities.length || new Set(value.priorities).size !== value.priorities.length || value.priorities.some(item => !priorities.includes(item))) throw new ContractError("Choose valid priorities, budget and existing-cover details.");
  return text(`Please help me understand health cover for this household. Adults to cover: ${value.adults}. Children to cover: ${value.children}. Eldest member age: ${value.age} completed years. Treatment city profile: ${value.city}. My priorities: ${value.priorities.join("; ") || "Not specified"}. My annual premium budget preference: ${value.budget}. Existing cover: ${value.cover}. Please ask for any missing details. These are preferences, not verified policy terms.`, 4000);
}
