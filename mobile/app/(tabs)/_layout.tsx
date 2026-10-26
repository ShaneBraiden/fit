import { Ionicons } from '@expo/vector-icons';
import { Redirect, Tabs } from 'expo-router';
import { useSession } from '../../lib/session';
import { useTheme } from '../../lib/theme';

const TABS: { name: string; title: string; icon: string }[] = [
  { name: 'today', title: 'Today', icon: 'today-outline' },
  { name: 'log', title: 'Record', icon: 'add-circle-outline' },
  { name: 'insights', title: 'Insights', icon: 'bulb-outline' },
  { name: 'routes', title: 'Routes', icon: 'map-outline' },
  { name: 'profile', title: 'Profile', icon: 'person-circle-outline' },
];

export default function TabsLayout() {
  const t = useTheme();
  const { ready, userId } = useSession();
  if (ready && userId == null) return <Redirect href="/" />;
  return (
    <Tabs screenOptions={{
      headerShown: false, tabBarActiveTintColor: t.accent, tabBarInactiveTintColor: t.muted,
      tabBarStyle: { backgroundColor: t.surface, borderTopColor: t.border },
      sceneStyle: { backgroundColor: t.page },
    }}>
      {TABS.map((tab) => (
        <Tabs.Screen key={tab.name} name={tab.name} options={{
          title: tab.title,
          tabBarIcon: ({ color, size }) => <Ionicons name={tab.icon as never} size={size} color={color} />,
        }} />
      ))}
    </Tabs>
  );
}
