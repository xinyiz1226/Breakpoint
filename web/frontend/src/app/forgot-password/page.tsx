import { Suspense } from "react";
import { AuthForm } from "@/components/auth-form";

export default function ForgotPage() {
  return <Suspense><AuthForm mode="forgot" /></Suspense>;
}
