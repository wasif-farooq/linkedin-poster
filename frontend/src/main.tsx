import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, Navigate, RouterProvider } from 'react-router'
import './index.css'
import { AppShell } from './layout/AppShell'
import { ChatPage } from './pages/ChatPage'
import { PlaceholderPage } from './pages/PlaceholderPage'
import { ReviewPage } from './pages/ReviewPage'

const router = createBrowserRouter([
  // Focused review mode: full screen, no sidebar (design: "Review draft").
  { path: 'chat/:threadId/review', element: <ReviewPage /> },
  {
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/chat" replace /> },
      { path: 'chat', element: <ChatPage /> },
      { path: 'chat/:threadId', element: <ChatPage /> },
      { path: 'history', element: <PlaceholderPage title="History" /> },
      { path: 'settings', element: <PlaceholderPage title="Health & settings" /> },
      { path: '*', element: <Navigate to="/chat" replace /> },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
