import { useEffect } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useAppStore } from '../src/stores/appStore';
import { useWebSocket } from '../src/services/ws';

export default function RootLayout() {
  const loadConfig = useAppStore((s) => s.loadConfig);
  const { isConnected } = useWebSocket();

  useEffect(() => {
    loadConfig();
  }, []);

  return (
    <>
      <StatusBar style="light" />
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: '#0D1117' },
          animation: 'slide_from_right',
        }}
      />
    </>
  );
}
