-- ---------- TAGS ----------
INSERT INTO tags (tag_id, name) VALUES
(1,  'Computer Science'),
(2,  'Machine Learning'),
(3,  'Deep Learning'),
(4,  'Mathematics'),
(5,  'Number Theory'),
(6,  'Geometry'),
(7,  'Physics'),
(8,  'Particle Physics'),
(9,  'Cosmology'),
(10, 'Chemistry'),
(11, 'Materials Science'),
(12, 'Biology'),
(13, 'Astrophysics');

-- ---------- L_RESOURCE ----------
INSERT INTO l_resource (l_resource_id, location, author, medium, title, description) VALUES
(1,  '/content/pdf/1706.03762.pdf', 'Ashish Vaswani et al.', 'PDF', 'Attention Is All You Need', 'Introduces the Transformer architecture, based solely on attention mechanisms, dispensing with recurrence and convolutions.'),
(2,  '/content/pdf/1406.2661.pdf', 'Ian J. Goodfellow et al.', 'PDF', 'Generative Adversarial Networks', 'Proposes a framework for estimating generative models via an adversarial process between a generator and discriminator.'),
(3,  '/content/pdf/1512.03385.pdf', 'Kaiming He et al.', 'PDF', 'Deep Residual Learning for Image Recognition', 'Introduces residual learning (ResNet) to ease training of very deep neural networks, winning ILSVRC 2015.'),
(4,  '/content/pdf/1810.04805.pdf', 'Jacob Devlin et al.', 'PDF', 'BERT: Pre-training of Deep Bidirectional Trans', 'Introduces BERT, a bidirectional Transformer pretraining approach for language understanding tasks.'),
(5,  '/content/pdf/1301.3781.pdf', 'Tomas Mikolov et al.', 'PDF', 'Efficient Estimation of Word Representations', 'Proposes two model architectures (word2vec) for computing continuous vector representations of words.'),
(6,  '/content/pdf/1412.6980.pdf', 'Diederik P. Kingma, Jimmy Ba', 'PDF', 'Adam: A Method for Stochastic Optimization', 'Introduces the Adam optimization algorithm for training deep learning models.'),
(7,  '/content/pdf/1511.06434.pdf', 'Alec Radford et al.', 'PDF', 'Unsupervised Representation Learning w/ DCGAN', 'Introduces DCGANs, deep convolutional GANs for unsupervised representation learning.'),
(8,  '/content/pdf/1505.04597.pdf', 'Olaf Ronneberger et al.', 'PDF', 'U-Net: Convolutional Networks for Biomed Seg', 'Introduces the U-Net architecture for biomedical image segmentation.'),
(9,  '/content/pdf/1703.10593.pdf', 'Jun-Yan Zhu et al.', 'PDF', 'Unpaired Image Translation (CycleGAN)', 'Introduces CycleGAN for unpaired image-to-image translation using cycle-consistent adversarial networks.'),
(10, '/content/pdf/1701.07875.pdf', 'Martin Arjovsky et al.', 'PDF', 'Wasserstein GAN', 'Proposes the Wasserstein distance as a training objective for GANs to improve training stability.'),
(11, '/content/pdf/1508.06576.pdf', 'Leon A. Gatys et al.', 'PDF', 'A Neural Algorithm of Artistic Style', 'Introduces neural style transfer, separating and recombining content and style of images using CNNs.'),
(12, '/content/pdf/1409.1556.pdf', 'Karen Simonyan, Andrew Zisserman', 'PDF', 'Very Deep Convolutional Networks (VGG)', 'Investigates the effect of convolutional network depth on accuracy in large-scale image recognition.'),
(13, '/content/pdf/1502.03167.pdf', 'Sergey Ioffe, Christian Szegedy', 'PDF', 'Batch Normalization', 'Introduces batch normalization to accelerate deep network training by reducing internal covariate shift.'),
(14, '/content/pdf/math_0404188.pdf', 'Ben Green, Terence Tao', 'PDF', 'Primes Contain Arbitrarily Long Arith. Progr.', 'Proves that the prime numbers contain arithmetic progressions of arbitrary length.'),
(15, '/content/pdf/math_0211159.pdf', 'Grigori Perelman', 'PDF', 'The Entropy Formula for the Ricci Flow', 'First of Perelman''s papers proving the Poincare and Geometrization conjectures via Ricci flow.'),
(16, '/content/pdf/math_0303109.pdf', 'Grigori Perelman', 'PDF', 'Ricci Flow with Surgery on 3-Manifolds', 'Second of Perelman''s papers, introducing Ricci flow with surgery for three-manifolds.'),
(17, '/content/pdf/math_0307245.pdf', 'Grigori Perelman', 'PDF', 'Finite Extinction Time for Ricci Flow', 'Third of Perelman''s papers, completing the proof of the Poincare conjecture.'),
(18, '/content/pdf/1207.7214.pdf', 'ATLAS Collaboration', 'PDF', 'Observation of a New Particle (ATLAS Higgs)', 'Reports the ATLAS detector observation of a new particle consistent with the Standard Model Higgs boson.'),
(19, '/content/pdf/1207.7235.pdf', 'CMS Collaboration', 'PDF', 'Observation of a New Boson at 125 GeV (CMS)', 'Reports the CMS detector observation of a new boson at a mass of 125 GeV, consistent with the Higgs boson.'),
(20, '/content/pdf/1602.03837.pdf', 'LIGO Scientific Collaboration', 'PDF', 'Observation of Gravitational Waves (LIGO)', 'Reports the first direct detection of gravitational waves, from a binary black hole merger.'),
(21, '/content/pdf/1807.06205.pdf', 'Planck Collaboration', 'PDF', 'Planck 2018 Results I: Overview', 'Overview paper for the final full-mission Planck cosmic microwave background results.'),
(22, '/content/pdf/1807.06209.pdf', 'Planck Collaboration', 'PDF', 'Planck 2018 Results VI: Cosmological Params', 'Presents cosmological parameter results from the final full-mission Planck CMB measurements.'),
(23, '/content/pdf/1807.06211.pdf', 'Planck Collaboration', 'PDF', 'Planck 2018 Results X: Constraints on Inflat', 'Reports implications of the 2018 Planck CMB anisotropy measurements for cosmic inflation.'),
(24, '/content/pdf/condmat_0410550.pdf', 'K. S. Novoselov et al.', 'PDF', 'Electric Field Effect in Thin Carbon Films', 'First isolation and characterization of graphene; work recognized by the 2010 Nobel Prize in Physics.'),
(25, '/content/pdf/condmat_0410631.pdf', 'K. S. Novoselov et al.', 'PDF', 'Room-Temp Electric Field Effect in Graphene', 'Reports room-temperature electric field effect and carrier-type inversion in graphene films.'),
(26, '/content/pdf/2212.07702.pdf', 'Arne Elofsson', 'PDF', 'Protein Structure Prediction until CASP15', 'Reviews advances in AI-based protein structure prediction sparked by the release of AlphaFold2.'),
(27, '/content/pdf/2505.22674.pdf', 'Multiple Authors', 'PDF', 'PSBench: Protein Structure Quality Benchmark', 'Introduces PSBench, a large benchmark dataset for evaluating protein complex structure model quality.');

-- ---------- L_RESOURCE_TAGS ----------
INSERT INTO l_resource_tags (l_resource_id, tag_id) VALUES
-- CS / ML papers -> Computer Science, Machine Learning, Deep Learning
(1,1),(1,2),(1,3),
(2,1),(2,2),(2,3),
(3,1),(3,2),(3,3),
(4,1),(4,2),(4,3),
(5,1),(5,2),
(6,1),(6,2),
(7,1),(7,2),(7,3),
(8,1),(8,2),(8,3),
(9,1),(9,2),(9,3),
(10,1),(10,2),(10,3),
(11,1),(11,2),(11,3),
(12,1),(12,2),(12,3),
(13,1),(13,2),(13,3),

-- Math papers -> Mathematics, Number Theory / Geometry
(14,4),(14,5),
(15,4),(15,6),
(16,4),(16,6),
(17,4),(17,6),

-- Physics papers -> Physics, Particle Physics / Cosmology / Astrophysics
(18,7),(18,8),
(19,7),(19,8),
(20,7),(20,13),
(21,7),(21,9),
(22,7),(22,9),
(23,7),(23,9),

-- Chemistry / Materials Science papers
(24,7),(24,10),(24,11),
(25,7),(25,10),(25,11),

-- Biology papers
(26,12),
(27,12);

-- ---------- HIGHLIGHTS ----------
-- Seed notes so the library has something to read back on a fresh install. Two
-- of these use colours outside the suggested palette, and every one carries a
-- comment, because both are what the reader is expected to add themselves.
INSERT INTO highlights (l_resource_highlight_id, l_resource_id, user_id, name, colour, quote, comment) VALUES
(1, 1, 1, 'Attention replaces recurrence', '#ffd54f',
 'We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely.',
 'The whole argument in one sentence: if attention alone can relate any two positions, the sequential bottleneck in RNNs was never necessary. Everything since follows from this.'),
(2, 1, 1, 'Why scaled dot product', '#90caf9',
 'We suspect that for large values of dk, the dot products grow large in magnitude, pushing the softmax function into regions where it has extremely small gradients.',
 'The 1/sqrt(dk) divisor is a variance fix, not an aesthetic choice. Worth remembering when a custom attention layer will not train.'),
(3, 3, 1, 'The degradation problem', '#a5d6a7',
 'When deeper networks are able to start converging, a degradation problem has been exposed: with the network depth increasing, accuracy gets saturated and then degrades rapidly.',
 'Key point I keep forgetting: this is not overfitting. Training error rises too, so it is an optimisation failure that the residual connection routes around.'),
(4, 6, 1, 'Adam defaults', '#f48fb1',
 'Good default settings for the tested machine learning problems are alpha = 0.001, beta1 = 0.9, beta2 = 0.999 and epsilon = 10^-8.',
 'These are the numbers every framework ships with. Cite this line rather than the framework docs.'),
(5, 15, 1, 'Ricci flow as heat equation', '#7e57c2',
 'The Ricci flow is the gradient flow for the functional F, and the monotonicity of F under the flow is what rules out the collapsing that earlier approaches could not exclude.',
 'Custom purple for the geometry reading. The entropy functional is the actual novelty here; the flow itself was already known from Hamilton.'),
(6, 18, 1, 'Five sigma', '#26a69a',
 'The observed excess of events over the expected background has a local significance of 5.9 standard deviations, corresponding to a background fluctuation probability of 1.7 x 10^-9.',
 'Custom teal for physics. Five sigma is the discovery threshold by convention, not by derivation, which is a point worth making in the write up.');

-- One rectangle per line of the quote, as fractions of the page box.
INSERT INTO highlight_rects (l_resource_highlight_id, page_number, x, y, width, height) VALUES
(1, 1, 0.130, 0.352, 0.740, 0.014),
(1, 1, 0.130, 0.368, 0.618, 0.014),
(2, 4, 0.130, 0.618, 0.742, 0.014),
(2, 4, 0.130, 0.634, 0.560, 0.014),
(3, 1, 0.130, 0.470, 0.744, 0.014),
(3, 1, 0.130, 0.486, 0.690, 0.014),
(4, 2, 0.130, 0.240, 0.706, 0.014),
(5, 1, 0.130, 0.286, 0.724, 0.014),
(5, 1, 0.130, 0.302, 0.588, 0.014),
(6, 1, 0.130, 0.540, 0.736, 0.014),
(6, 1, 0.130, 0.556, 0.604, 0.014);
