import { Ionicons } from '@expo/vector-icons';
import { Redirect, Tabs } from 'expo-router';
import { useSession } from '../../lib/session';
import { useTheme } from '../../lib/theme';

const TABS: { name: string; title: string; icon: string; hidden?: boolean }[] = [
  { name: 'today', title: 'Today', icon: 'today-outline' },
  { name: 'log', title: 'Record', icon: 'add-circle-outline' },
  { name: 'muscles', title: 'Muscles', icon: 'body-outline' },
  { name: 'friends', title: 'Friends', icon: 'people-outline' },
  { name: 'profile', title: 'Profile', icon: 'person-circle-outline' },
  // Reached from Today (and each other), with the tab bar still showing.
  { name: 'plan', title: 'Plan', icon: 'calendar-outline', hidden: true },
  { name: 'streak', title: 'Streak', icon: 'flame-outline', hidden: true },
  { name: 'insights', title: 'Insights', icon: 'bulb-outline', hidden: true },
  { name: 'routes', title: 'Routes', icon: 'map-outline', hidden: true },
];

export default function TabsLayout() {
  const t = useTheme();
  const { ready, token } = useSession();
  if (ready && !token) return <Redirect href="/" />;
  return (
    <Tabs backBehavior="history" screenOptions={{
      headerShown: false, tabBarActiveTintColor: t.accent, tabBarInactiveTintColor: t.muted,
      tabBarStyle: { backgroundColor: t.surface, borderTopColor: t.border },
      sceneStyle: { backgroundColor: t.page },
    }}>
      {TABS.map((tab) => (
        <Tabs.Screen key={tab.name} name={tab.name} options={{
          title: tab.title, href: tab.hidden ? null : undefined,
          tabBarIcon: ({ color, size }) => <Ionicons name={tab.icon as never} size={size} color={color} />,
        }} />
      ))}
    </Tabs>
  );
}
