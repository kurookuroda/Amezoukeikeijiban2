#!/usr/bin/perl
use strict;
use warnings;
use FindBin qw($Bin);
chdir($Bin);   # 相対パスで動くので、カレントをスクリプトのあるディレクトリに固定する

my $copyright = <<EOL;
<!-- 
     Script for amezo-like BBS HEAD LINE
     Copyright (C) 2000 amezo_
     http://www17.big.or.jp/~amezo_/
-->
EOL

# クエリ文字列が付いていたら、自分自身のソースを返して終了
if(defined $ENV{'QUERY_STRING'} && length $ENV{'QUERY_STRING'}){
	print "Content-type: text/plain; charset=UTF-8\n\n";
	if(open(my $src, '<', './dai.cgi')){
		print $_ while <$src>;
		close($src);
	}
	exit;
}

print "Content-type: text/html; charset=UTF-8\n\n";
print '<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">' . "\n";
print '<meta name="viewport" content="width=device-width, initial-scale=1">' . "\n";

if(open(my $bl, '<', './blist.txt')){
	while(my $line = <$bl>){
		$line =~ s/\r?\n\z//;
		my ($folder, $color, $title) = split(/,/, $line);
		next unless defined $folder && length $folder;
		next if $folder =~ /^\./;          # 板名が . で始まる板は隠し板
		$color = '' unless defined $color;
		$title = '' unless defined $title;
		$color =~ s/!.*//;                 # 背景画像の指定(!以降)を除く
		$color =~ s/\*$//;                 # 白文字モードの印(*)を除く
		$title =~ s/#c#/,/g;               # #c# はカンマの代わり
		print <<EOF;
<table border=0 cellspacing=1 cellpadding=2 width=100% bgcolor="$color"><tr><td>
<a href="$folder/" target="naka"><b><font size="3" color="#F92500">$title</font></b></a> 
EOF
		if(open(my $r, '<', "./$folder/index.html")){
			while(my $l = <$r>){
				last if $l =~ /<!-- HEAD LINE -->/;
			}
			for(my $i = 0; $i < 20; $i++){
				my $l = <$r>;
				last unless defined $l;
				last if $l =~ /<!-- HEAD LINE END -->/;
				$l =~ s/(\d+\.html)/$folder\/$1/;
				print $l;
			}
			close($r);
		}
		print "</td></tr></table>\n";
	}
	close($bl);
}