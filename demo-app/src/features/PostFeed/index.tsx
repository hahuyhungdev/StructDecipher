/**
 * Feature: Post Feed - displays recent posts.
 */
import { useEffect, useState } from "react";
import { useTracking } from "../../hooks/useTracking";
import { fetchPosts } from "../../services/api";
import Card from "../../components/Card";

interface Post {
  id: number;
  title: string;
  body: string;
}

export default function PostFeed() {
  const { trackApiCall } = useTracking("PostFeed", {
    filePath: "src/features/PostFeed.tsx",
  });
  const [posts, setPosts] = useState<Post[]>([]);

  useEffect(() => {
    trackApiCall("/posts");
    fetchPosts().then(setPosts);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div>
      <h2>Recent Posts</h2>
      {posts.map((p) => (
        <Card key={p.id} title={p.title}>
          <p style={{ fontSize: 14, color: "#6b7280" }}>{p.body}</p>
        </Card>
      ))}
    </div>
  );
}
