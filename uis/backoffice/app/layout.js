import "./globals.css";
import { AuthProvider } from "../components/AuthProvider";
import NavBar from "../components/NavBar";

export const metadata = {
  title: "Company Backoffice",
  description: "Authenticated internal backoffice",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          <NavBar />
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}
