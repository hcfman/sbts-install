#!/usr/bin/perl

my $filename = "/etc/apache2/apache2.conf";
open my $in, '<', $filename or die "Can't open $filename: $!\n";

my $l;
do { local $/; $l = <$in> };
close $in;

my $piece = $1 if $l =~ m%(<Directory /var/www/.*?</Directory>)%s;

if ( $piece !~ m%Options%s ) {
    exit 0;
}

$piece =~ s%^.*?Options.*?\n%%m;
$l =~ s%<Directory /var/www/.*?</Directory>%$piece%s;

open my $out, '>', $filename or die "Can't re-write $filename: $!\n";
print $out $l;
close $out;

exit 0;
