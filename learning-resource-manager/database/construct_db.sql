CREATE TABLE l_resource( 
	l_resource_id INTEGER PRIMARY KEY,
	author VARCHAR(50),
	medium VARCHAR(32) NOT NULL,
	title VARCHAR(50) NOT NULL,
	description TEXT
);

CREATE TABLE subjects(
	subject_id INTEGER PRIMARY KEY,
	name VARCHAR(32)
);

CREATE TABLE l_resource_subject(
	l_resource_id INTEGER NOT NULL,
	subject_id INTEGER NOT NULL,

	PRIMARY KEY (l_resource_id, subject_id),
	CONSTRAINT FK_l_resource_id FOREIGN KEY (l_resource_id) REFERENCES l_resource(l_resource_id),
	CONSTRAINT FK_subject_id FOREIGN KEY (subject_id) REFERENCES subjects(subject_id)
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
