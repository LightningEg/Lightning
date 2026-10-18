export const COMMAND = {
  name: 'lightning', description: 'Lightning community tools', type: 1,
  options: [
    { type: 1, name: 'ping', description: 'Check that Lightning bot responds' },
    { type: 1, name: 'post', description: 'Post a channel announcement (operators only)', options: [
      { type: 7, name: 'channel', description: 'Target text channel', required: true, channel_types: [0] },
      { type: 3, name: 'message', description: 'Announcement text (mentions are disabled)', required: true, max_length: 1900 }
    ] },
    { type: 1, name: 'channel', description: 'Create a text channel (operators only)', options: [
      { type: 3, name: 'name', description: 'Lowercase name with hyphens', required: true, max_length: 80 },
      { type: 3, name: 'topic', description: 'Optional topic', max_length: 1024 }
    ] },
    { type: 1, name: 'forum', description: 'Create a forum channel (operators only)', options: [
      { type: 3, name: 'name', description: 'Lowercase name with hyphens', required: true, max_length: 80 },
      { type: 3, name: 'topic', description: 'Optional topic', max_length: 1024 }
    ] },
    { type: 1, name: 'thread', description: 'Start a public thread (operators only)', options: [
      { type: 7, name: 'channel', description: 'Parent text channel', required: true, channel_types: [0] },
      { type: 3, name: 'name', description: 'Thread title', required: true, max_length: 100 },
      { type: 3, name: 'message', description: 'Opening message', required: true, max_length: 1900 }
    ] },
    { type: 1, name: 'feedback', description: 'Send feedback privately to the Lightning team', options: [
      { type: 3, name: 'topic', description: 'Short title', required: true, max_length: 100 },
      { type: 3, name: 'details', description: 'Feedback, without personal or financial information', required: true, max_length: 1600 }
    ] }
  ]
};
