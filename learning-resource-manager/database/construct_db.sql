CREATE TABLE l_resource( 
	l_resource_id INTEGER PRIMARY KEY,
	location VARCHAR(150) NOT NULL,
	author VARCHAR(150),
	medium VARCHAR(32) NOT NULL,
	title VARCHAR(50) NOT NULL,
	description TEXT
);

CREATE TABLE tags(
	tag_id INTEGER PRIMARY KEY,
	name VARCHAR(30) NOT NULL
);

CREATE TABLE l_resource_tags(
	l_resource_id INTEGER NOT NULL,
	tag_id INTEGER NOT NULL,

	PRIMARY KEY (l_resource_id, tag_id),
	CONSTRAINT FK_l_resource_id FOREIGN KEY (l_resource_id) REFERENCES l_resource(l_resource_id),
	CONSTRAINT FK_tag_id FOREIGN KEY (tag_id) REFERENCES tags(tag_id)
);

-- A snippet someone kept from a resource. Rows and characters do not exist in a
-- PDF, so the position lives in highlight_rects rather than here; this table is
-- what the snippet is called, how it looks, what it said and what the reader
-- made of it.
CREATE TABLE highlights(
	l_resource_highlight_id INTEGER PRIMARY KEY,
	l_resource_id INTEGER NOT NULL,
	user_id INTEGER NOT NULL,
	name VARCHAR(64),
	-- Any '#rrggbb' the reader picks, not just the suggested palette.
	colour VARCHAR(16) NOT NULL,
	quote TEXT,
	-- What the reader wrote about the quote, as opposed to the quote itself.
	comment TEXT,
	created_at TEXT NOT NULL DEFAULT (datetime('now')),
	CONSTRAINT FK_highlight_resource FOREIGN KEY (l_resource_id) REFERENCES l_resource(l_resource_id)
);

-- One selection covers a rectangle per line of text, so a highlight owns many.
-- Coordinates are fractions of the page box (0 to 1) rather than pixels, so they
-- survive the page being rendered at any width.
CREATE TABLE highlight_rects(
	highlight_rect_id INTEGER PRIMARY KEY,
	l_resource_highlight_id INTEGER NOT NULL,
	page_number INTEGER NOT NULL,
	x REAL NOT NULL,
	y REAL NOT NULL,
	width REAL NOT NULL,
	height REAL NOT NULL,
	CONSTRAINT FK_rect_highlight FOREIGN KEY (l_resource_highlight_id) REFERENCES highlights(l_resource_highlight_id)
);

-- The fields the resource grid renders on each card.
CREATE VIEW v_resource_card AS
	SELECT l_resource_id,
	       title,
	       author,
	       description,
	       location
	FROM l_resource
	ORDER BY title;

-- One row per highlight for the resource popup: what it is called and the first
-- page it lands on, which is where following it should jump to.
CREATE VIEW v_highlight_summary AS
	SELECT h.l_resource_id,
	       h.l_resource_highlight_id,
	       h.name,
	       h.colour,
	       h.quote,
	       h.comment,
	       MIN(r.page_number) AS page_number,
	       COUNT(r.highlight_rect_id) AS rect_count
	FROM highlights h
	JOIN highlight_rects r ON r.l_resource_highlight_id = h.l_resource_highlight_id
	GROUP BY h.l_resource_highlight_id
	ORDER BY MIN(r.page_number), h.created_at;

-- Every rectangle the reader has to draw, carrying the highlight it belongs to.
CREATE VIEW v_highlight_rect AS
	SELECT h.l_resource_id,
	       h.l_resource_highlight_id,
	       h.name,
	       h.colour,
	       h.quote,
	       h.comment,
	       r.page_number,
	       r.x,
	       r.y,
	       r.width,
	       r.height
	FROM highlights h
	JOIN highlight_rects r ON r.l_resource_highlight_id = h.l_resource_highlight_id
	ORDER BY r.page_number, r.y;

-- Every resource with its tags collapsed onto one row, for the chat service to
-- hand to the language model whole.
CREATE VIEW v_resource_catalogue AS
	SELECT r.l_resource_id,
	       r.title,
	       r.author,
	       r.medium,
	       r.description,
	       GROUP_CONCAT(t.name, ', ') AS tags
	FROM l_resource r
	LEFT JOIN l_resource_tags rt ON rt.l_resource_id = r.l_resource_id
	LEFT JOIN tags t ON t.tag_id = rt.tag_id
	GROUP BY r.l_resource_id
	ORDER BY r.title;

-- Every highlight with the resource and tags it sits under, for the chat service
-- to hand to the language model whole. Built on the two views above so the
-- rectangles are already collapsed to a page and the tags to one string: joining
-- both directly here would multiply the rows and repeat every tag.
CREATE VIEW v_highlight_catalogue AS
	SELECT h.l_resource_highlight_id,
	       h.l_resource_id,
	       c.title,
	       c.tags,
	       h.name,
	       h.quote,
	       h.comment,
	       h.page_number
	FROM v_highlight_summary h
	JOIN v_resource_catalogue c ON c.l_resource_id = h.l_resource_id
	ORDER BY c.title, h.page_number;
