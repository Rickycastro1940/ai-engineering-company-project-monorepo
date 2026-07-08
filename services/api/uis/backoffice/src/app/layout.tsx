import React from 'react';

export const metadata = {
  title: 'Backoffice Inventory',
  description: 'Backoffice inventory workspace',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: 'sans-serif', background: '#f8fafc', color: '#101828' }}>
        {children}
      </body>
    </html>
  );
}
