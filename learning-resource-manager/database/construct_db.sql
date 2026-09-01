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

CREATE TABLE highlights(
	l_resource_highlight_id INTEGER PRIMARY KEY,
	l_resource_id INTEGER NOT NULL,
	user_id INTEGER NOT NULL,
	name VARCHAR(32),
	begin_row INTEGER NOT NULL,
	begin_char INTEGER NOT NULL,
	end_row INTEGER NOT NULL,
	end_char INTEGER NOT NULL,
	CONSTRAINT FK_highlight_resource FOREIGN KEY (l_resource_id) REFERENCES l_resource(l_resource_id)
);

-- The fields the resource grid renders on each card.
CREATE VIEW v_resource_card AS
	SELECT title,
	       author,
	       description,
	       location
	FROM l_resource
	ORDER BY title;

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
