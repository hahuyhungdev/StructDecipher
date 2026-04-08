/**
 * Feature: User List - displays a list of users from the API.
 */
import { useEffect, useState } from "react";
import { useTracking } from "../hooks/useTracking";
import { fetchUsers } from "../services/api";
import Card from "../components/Card";
import Button from "../components/Button";

interface User {
  id: number;
  name: string;
  email: string;
}

export default function UserList() {
  const { trackClick, trackApiCall } = useTracking("UserList", {
    filePath: "src/features/UserList.tsx",
  });
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(false);

  const loadUsers = async () => {
    trackClick("load_users");
    trackApiCall("/users");
    setLoading(true);
    try {
      const data = await fetchUsers();
      setUsers(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadUsers();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div>
      <h2>Users</h2>
      <Button
        label={loading ? "Loading..." : "Refresh Users"}
        onClick={loadUsers}
      />
      <div style={{ marginTop: 12 }}>
        {users.map((u) => (
          <Card key={u.id} title={u.name}>
            <p>{u.email}</p>
          </Card>
        ))}
      </div>
    </div>
  );
}
