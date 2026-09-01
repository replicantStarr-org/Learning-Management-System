INSERT INTO subjects (subject_id, name) VALUES
(1, 'Computer Science'),
(2, 'Mathematics'),
(3, 'Physics'),
(4, 'Machine Learning');

INSERT INTO l_resource (l_resource_id, author, medium, title, description) VALUES
(1, 'Vaswani et al.', 'PDF', 'Attention Is All You Need', 'Introduces the Transformer architecture, replacing recurrence with self-attention for sequence modeling.'),
(2, 'Kaiming He et al.', 'PDF', 'Deep Residual Learning for Image Recognition', 'Introduces ResNet, using residual connections to enable training of very deep neural networks.'),
(3, 'Volodymyr Mnih et al.', 'PDF', 'Playing Atari with Deep Reinforcement Learning', 'Presents the Deep Q-Network (DQN), combining reinforcement learning with deep neural networks to play Atari games from pixels.'),
(4, 'Claude Shannon', 'PDF', 'A Mathematical Theory of Communication', 'Foundational paper establishing information theory, defining entropy and the limits of data compression and transmission.'),
(5, 'Grigori Perelman', 'PDF', 'Entropy Formula for Ricci Flow', 'Presents key results used in the proof of the Poincare Conjecture via Ricci flow techniques.'),
(6, 'ATLAS Collaboration', 'PDF', 'Observation of the Higgs Boson', 'Reports the discovery of a new particle consistent with the Standard Model Higgs boson at the LHC.'),
(7, 'LIGO Scientific Collab.', 'PDF', 'Observation of Gravitational Waves', 'Reports the first direct detection of gravitational waves from a binary black hole merger.');

INSERT INTO l_resource_subject (l_resource_id, subject_id) VALUES
(1, 1),
(1, 4),
(2, 1),
(2, 4),
(3, 1),
(3, 4),
(4, 1),
(4, 2),
(5, 2),
(6, 3),
(7, 3);
